# Avisos de vencimiento de matrices globales activas al administrador de la plataforma (services/matrixExpiryAlerts.py).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_matrix_expiry_alerts.py -v

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.matrix import Matrix
from app.models.notificationEvents import PLATAFORMA_MATRIZ_VENCIMIENTO
from app.models.userNotification import UserNotification
from app.schemas.matrix import MatrixCreateRequest
from app.services import matrix as matrices
from app.services import matrixExpiryAlerts as alerts
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    db,
    engine,
    mails,
    makeUser,
    reload,
)
from tests.test_matrices import rule


@pytest.fixture
def admin(db, mails):
    return makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin-vigencia@example.com", usuario="adminvigencia")


@pytest.fixture
def moderator(db, mails):
    return makeUser(db, tipoCuenta="MODERADOR_PLATAFORMA", email="moderacion-vigencia@example.com", usuario="modvigencia")


def activeUntil(db, actor, diasRestantes: int, nombre="Matriz GlucoLume") -> Matrix:
    """Matriz global ACTIVA cuyo último día es hoy + diasRestantes. Desde hace 10 días, para que la activación sea válida."""
    today = nowForDb().date()
    created = matrices.createMatrix(db, actor, MatrixCreateRequest(
        referenciaBase="Fuente de prueba", ambito="GLOBAL", nombre=nombre,
        fechaVigenciaDesde=today - timedelta(days=10), fechaVigenciaHasta=today + timedelta(days=diasRestantes),
        reglas=[rule()]))
    matrices.activate(db, actor, created.idMatriz)
    return db.get(Matrix, created.idMatriz)


def atDay(days: int = 0, hours: int = 0):
    """Instante de una pasada: hoy + días/horas (hora de Argentina, como la lógica de la aplicación)."""
    return nowForDb() + timedelta(days=days, hours=hours)


def avisos(db, user):
    return list(db.scalars(select(UserNotification).where(
        UserNotification.idUsuario == user.idUsuario, UserNotification.evento == PLATAFORMA_MATRIZ_VENCIMIENTO)).all())


def test_los_umbrales_son_10_5_3_2_y_1_dia_y_el_mas_ajustado_gana():
    assert [alerts.umbralPara(d) for d in (11, 10, 9, 6, 5, 4, 3, 2, 1, 0, -1)] == [None, 10, 10, 10, 5, 5, 3, 2, 1, 1, None]


def test_avisa_al_llegar_a_cada_umbral_una_sola_vez(db, admin):
    matrix = activeUntil(db, admin, 10)
    assert alerts.run(db, atDay(0)) == {"avisos": 1}  # faltan 10 días
    assert alerts.run(db, atDay(0, hours=3)) == {"avisos": 0}  # misma pasada repetida: nada
    assert alerts.run(db, atDay(1)) == {"avisos": 0}  # faltan 9 días: sigue en el umbral 10
    assert alerts.run(db, atDay(5)) == {"avisos": 1}  # faltan 5: umbral 5
    assert len(avisos(db, admin)) == 2
    assert reload(db, Matrix, matrix.idMatriz).avisoVencimientoNivel == 5


def test_el_aviso_nombra_la_matriz_su_version_y_lleva_a_su_detalle(db, admin):
    matrix = activeUntil(db, admin, 3, nombre="Matriz de prueba")
    alerts.run(db, atDay(0))
    [aviso] = avisos(db, admin)
    assert "Matriz de prueba" in aviso.mensaje and "versión 1" in aviso.mensaje and "activa" in aviso.mensaje
    assert aviso.url == f"/app/matrices/{matrix.idMatriz}"


def test_si_la_pasada_se_retrasa_avisa_solo_el_umbral_mas_ajustado(db, admin):
    activeUntil(db, admin, 10)
    assert alerts.run(db, atDay(6)) == {"avisos": 1}  # faltan 4 días: un solo aviso (el de 5), no uno por cada umbral saltado
    assert alerts.run(db, atDay(7)) == {"avisos": 1}  # faltan 3: el umbral 3 sí corresponde
    assert len(avisos(db, admin)) == 2


def test_faltando_un_dia_y_el_dia_del_vencimiento_avisan_los_umbrales_1_y_luego_vencida(db, admin):
    activeUntil(db, admin, 3)
    assert [alerts.run(db, atDay(d))["avisos"] for d in (0, 1, 2, 3)] == [1, 1, 1, 0]  # 3, 2 y 1 días; «vence hoy» ya avisado
    assert alerts.run(db, atDay(4)) == {"avisos": 1}  # ya venció: primer aviso de vencida
    assert alerts.run(db, atDay(4, hours=23)) == {"avisos": 0}  # dentro de las 24 h no repite
    assert alerts.run(db, atDay(5, hours=1)) == {"avisos": 1}  # pasadas 24 h: repite mientras los reciba
    assert len(avisos(db, admin)) == 5
    assert any("venció" in a.mensaje for a in avisos(db, admin))


def test_el_administrador_puede_desactivar_los_avisos_en_cualquier_momento_y_no_llega_ninguno(db, admin):
    matrix = activeUntil(db, admin, 10)
    detail = matrices.setExpiryAlert(db, admin, matrix.idMatriz, recibir=False)  # antes de vencer, sin esperar a que venza
    assert detail.avisoVencimientoSilenciado is True and detail.permisos.puedeCambiarAvisoVencimiento is True
    assert alerts.run(db, atDay(0)) == {"avisos": 0}  # faltan 10 días: no sale
    assert alerts.run(db, atDay(5)) == {"avisos": 0}  # faltan 5: tampoco
    assert avisos(db, admin) == []
    assert reload(db, Matrix, matrix.idMatriz).nombre == "Matriz GlucoLume"  # la matriz no cambia


def test_al_volver_a_recibirlos_sale_el_aviso_de_la_fecha_actual_sin_repetir_los_ya_enviados(db, admin):
    matrix = activeUntil(db, admin, 10)
    alerts.run(db, atDay(0))  # 10 días: enviado
    matrices.setExpiryAlert(db, admin, matrix.idMatriz, recibir=False)
    assert alerts.run(db, atDay(6)) == {"avisos": 0}  # faltan 4 días, desactivado: no sale nada
    matrices.setExpiryAlert(db, admin, matrix.idMatriz, recibir=True)
    assert alerts.run(db, atDay(6)) == {"avisos": 1}  # reactivado: el de 5 (el de 10 ya se envió antes)
    assert len(avisos(db, admin)) == 2


def test_el_aviso_vencida_se_puede_desactivar_y_volver_a_activar(db, admin):
    matrix = activeUntil(db, admin, 1)
    matrix = reload(db, Matrix, matrix.idMatriz)
    matrix.fechaVigenciaHasta = nowForDb().date() - timedelta(days=1)
    db.commit()
    assert alerts.run(db, atDay(0)) == {"avisos": 1}
    matrices.setExpiryAlert(db, admin, matrix.idMatriz, recibir=False)
    assert alerts.run(db, atDay(3)) == {"avisos": 0}
    matrices.setExpiryAlert(db, admin, matrix.idMatriz, recibir=True)
    assert alerts.run(db, atDay(3)) == {"avisos": 1}


def test_el_moderador_no_cambia_el_aviso_del_administrador(db, admin, moderator):
    matrix = activeUntil(db, admin, 1)
    with pytest.raises(AuthError) as error:
        matrices.setExpiryAlert(db, moderator, matrix.idMatriz, recibir=False)
    assert error.value.code == "PERMISO_INSUFICIENTE"
    assert reload(db, Matrix, matrix.idMatriz).avisoVencimientoSilenciado is False


def test_solo_se_cambia_el_aviso_de_una_matriz_global_activa(db, admin):
    borrador = matrices.createMatrix(db, admin, MatrixCreateRequest(referenciaBase="Fuente de prueba", ambito="GLOBAL", nombre="Borrador"))
    with pytest.raises(AuthError) as error:
        matrices.setExpiryAlert(db, admin, borrador.idMatriz, recibir=False)
    assert error.value.code == "MATRIZ_ESTADO_INVALIDO"


def test_sin_administrador_no_se_reserva_nada_y_el_aviso_sale_cuando_lo_hay(db, moderator):
    # Sin administrador activo, la pasada no reserva el umbral: el aviso sale cuando haya quien lo reciba.
    matrix = activeUntil(db, moderator, 10)
    assert alerts.run(db, atDay(0)) == {"avisos": 0}
    assert reload(db, Matrix, matrix.idMatriz).avisoVencimientoNivel is None
    later = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin-nuevo@example.com", usuario="adminnuevo")
    assert alerts.run(db, atDay(0)) == {"avisos": 1}
    assert len(avisos(db, later)) == 1


def test_el_correo_al_administrador_lleva_al_detalle_de_la_matriz(db, admin, mails):
    matrix = activeUntil(db, admin, 3, nombre="Matriz de prueba")
    mails.clear()
    alerts.run(db, atDay(0))
    [correo] = [m for m in mails if m["to"] == admin.correoElectronico]
    assert correo["subject"] == "Una matriz de GlucoLume está por vencer"
    assert f"/app/matrices/{matrix.idMatriz}" in correo["html"]
    assert "Matriz de prueba" in correo["html"]
    assert "crear una versión nueva" in correo["html"]

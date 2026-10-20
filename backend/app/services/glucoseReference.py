# Matriz de referencia de glucosa de una medición en modo GLUCOSA_EXPERIMENTAL (solo lectura, para el detalle).
#
# Distingue tres cosas y nunca las mezcla:
#   · APLICADA   — la matriz participó en una estimación del servidor (`glucosaEstimada` existe) con una regla guardada.
#   · REFERENCIA — la matriz se consulta para COMPARAR el valor (p. ej. el que informó el firmware); no participó en ningún cálculo.
#   · SIN_MATRIZ — no había información aplicable.
# Lee la matriz que quedó asociada a la medición (`idMatriz`: ya trae su versión), así que una versión posterior no reclasifica el pasado.
# Los reglas son las reales de ReglaMatriz. «Dentro / por debajo / por encima» es una comparación matemática con el intervalo
# configurado, NO una clasificación clínica. Si el sexo o la edad no se informaron NO se elige una regla: se muestran las disponibles
# (ambos sexos, sin posición) para consulta. Nada de esto modifica la medición ni el perfil.

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import ORIGEN_DEMO, Measurement
from app.schemas.measurement import GlucoseReference, MatrixSummary, ReferenceGroup, ReferenceRule
from app.services import schemaCompat

SEX_TITLES = {"FEMENINO": "Referencia femenina", "MASCULINO": "Referencia masculina",
              "NO_INFORMADO": "Referencia para sexo no informado"}
SEX_NOT_INFORMED = ("El sexo no fue informado. Se muestran ambas referencias únicamente para consulta. Ninguna se asigna automáticamente a tu "
                    "perfil ni se utiliza como resultado personalizado.")


def _minutes(measurement: Measurement) -> int | None:
    if measurement.fechaHoraUltimaComida is None:
        return None
    return int((measurement.fechaHoraInicio - measurement.fechaHoraUltimaComida).total_seconds() // 60)


def _ruleRead(rule: MatrixRule) -> ReferenceRule:
    return ReferenceRule(
        idRegla=rule.idReglaMatriz, codigo=rule.codigoRegla, sexoModelo=rule.sexoModelo, edadDesde=rule.edadDesde, edadHasta=rule.edadHasta,
        condicionComida=rule.condicionComida, minutosComidaMin=rule.minutosComidaMin, minutosComidaMax=rule.minutosComidaMax,
        glucosaMinReferencia=float(rule.glucosaMinReferencia), glucosaMaxReferencia=float(rule.glucosaMaxReferencia))


def _inAge(rule: MatrixRule, age: int) -> bool:
    """Un límite de edad vacío (NULL) es «sin límite»: nunca se compara contra None."""
    return (rule.edadDesde is None or rule.edadDesde <= age) and (rule.edadHasta is None or age <= rule.edadHasta)


def _ageless(rule: MatrixRule) -> bool:
    return rule.edadDesde is None and rule.edadHasta is None


def _foodMatches(rule: MatrixRule, condition: str, minutes: int | None) -> bool:
    if condition == "NO_INFORMADA":
        return True  # sin dato de alimentación no se descarta ninguna regla (luego se prefieren las previstas para ese caso)
    if rule.condicionComida != condition:
        return False
    if condition == "POSTPRANDIAL" and minutes is not None:
        return ((rule.minutosComidaMin is None or minutes >= rule.minutosComidaMin)
                and (rule.minutosComidaMax is None or minutes <= rule.minutosComidaMax))
    return True


def position(rule: ReferenceRule | None, value: float | None) -> str | None:
    if rule is None or value is None:
        return None
    if value < rule.glucosaMinReferencia:
        return "POR_DEBAJO"
    if value > rule.glucosaMaxReferencia:
        return "POR_ENCIMA"
    return "DENTRO"


def build(db: Session, measurement: Measurement) -> GlucoseReference:
    estimated = measurement.glucosaEstimada is not None
    raw = measurement.glucosaEstimada if estimated else measurement.glucosaDispositivo
    value = float(raw) if raw is not None else None
    origin = measurement.origenGlucosa or ("EXPERIMENTAL" if estimated else None)
    common = dict(valor=value, unidad="mg/dL", origen=origin, esDemo=measurement.origenGlucosa == ORIGEN_DEMO,
                  sexoInformado=measurement.sexoModelo is not None, edadInformada=measurement.edadAlMomento is not None,
                  condicionComida=measurement.condicionComida, minutosDesdeUltimaComida=_minutes(measurement),
                  edad=measurement.edadAlMomento, sexoModelo=measurement.sexoModelo)
    matrix = db.get(Matrix, measurement.idMatriz) if measurement.idMatriz else None
    if matrix is None:
        return GlucoseReference(estado="SIN_MATRIZ", matriz=None, grupos=[], avisoSexo=None, **common)

    rules = db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == matrix.idMatriz)
                       .order_by(MatrixRule.sexoModelo, MatrixRule.edadDesde, MatrixRule.condicionComida, MatrixRule.codigoRegla)).all()
    minutes = _minutes(measurement)
    age = measurement.edadAlMomento
    appliedRule = schemaCompat.ruleIdOf(db, measurement.idMedicion)
    condition = measurement.condicionComida
    # Sexo informado: solo su referencia. Sin informar: ambas (solo para consulta) y, si la matriz las trae, las previstas para «sexo no informado».
    sexes = [measurement.sexoModelo] if measurement.sexoModelo else ["FEMENINO", "MASCULINO"]
    if measurement.sexoModelo is None and any(r.sexoModelo == "NO_INFORMADO" for r in rules):
        sexes.append("NO_INFORMADO")
    groups: list[ReferenceGroup] = []
    for sex in sexes:
        ofSex = [r for r in rules if r.sexoModelo == sex and _foodMatches(r, condition, minutes)]
        foodExact = condition in ("AYUNO",) or (condition == "POSTPRANDIAL" and minutes is not None)
        if condition == "NO_INFORMADA":  # se prefieren las reglas previstas justamente para «alimentación no informada»
            exact = [r for r in ofSex if r.condicionComida == "NO_INFORMADA"]
            if exact:
                ofSex, foodExact = exact, True
        inRange = [r for r in ofSex if age is None or _inAge(r, age)]
        # Con la edad conocida corresponde la regla de su franja; la de «edad no especificada» (sin rango) es para cuando no se conoce.
        candidates = ([r for r in inRange if not _ageless(r)] or inRange) if age is not None else inRange
        selected = None
        reason = None
        if not candidates:
            reason = "Referencia no disponible."
        elif age is None:
            ageless = [r for r in candidates if _ageless(r)]
            if len(ageless) == 1 and foodExact:
                selected = ageless[0]  # regla prevista para edad no especificada (no se inventa ningún rango etario)
            else:
                reason = ("La edad no fue informada: no puede seleccionarse una referencia personalizada. Se muestran las reglas disponibles con "
                          "sus rangos de edad.")
        elif not foodExact:
            reason = "La condición de alimentación no está determinada: se muestran las reglas disponibles sin elegir una."
        elif len(candidates) > 1:
            reason = "Hay más de una regla posible para este contexto: se muestran todas sin elegir una."
        else:
            selected = candidates[0]
        read = _ruleRead(selected) if selected is not None else None
        groups.append(ReferenceGroup(
            sexoModelo=sex, titulo=SEX_TITLES.get(sex, f"Referencia {sex}"), reglas=[_ruleRead(r) for r in candidates],
            reglaSeleccionada=read, posicion=position(read, value), motivoSinSeleccion=reason,
            aplicada=bool(selected is not None and estimated and appliedRule == selected.idReglaMatriz)))
    return GlucoseReference(
        estado="APLICADA" if estimated else "REFERENCIA",
        matriz=MatrixSummary(idMatriz=matrix.idMatriz, nombre=matrix.nombre, version=matrix.version, ambito=matrix.ambito),
        grupos=groups, avisoSexo=SEX_NOT_INFORMED if measurement.sexoModelo is None else None, **common)

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { clearTokens, saveTokens } from "../../../auth/tokenStore.js";
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from "../../../test/helpers.js";
import { renderAt } from "../../../test/renderApp.jsx";

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: "USUARIO_INSTITUCIONAL" } };
const ID = "9a000000-0000-4000-8000-000000000001";
const BASE = `/institutions/${ID}`;
const PERMISOS = {
  PROPIETARIO: ["CONSULTAR_INSTITUCION", "GESTIONAR_MODERADORES", "ADMINISTRAR_OPERADORES", "CONSULTAR_EQUIPO", "CONSULTAR_PACIENTES"],
  MODERADOR: ["CONSULTAR_INSTITUCION", "INCORPORAR_OPERADORES", "ADMINISTRAR_OPERADORES", "CONSULTAR_EQUIPO", "CONSULTAR_PACIENTES"],
  OPERADOR: ["CONSULTAR_INSTITUCION", "CONSULTAR_PACIENTES"],
};

const detail = (rol) => ({
  idInstitucion: ID, nombre: "Prueba", tipoInstitucion: "CLINICA", estado: "ACTIVA", rolInstitucion: rol, estadoRelacion: "ACTIVO",
  permisos: PERMISOS[rol], tipoIdentificadorLegal: "CUIT", identificadorLegal: "30712345671", descripcion: null,
  fechaCreacion: "2026-10-01T10:00:00", fechaActualizacion: "2026-10-01T10:00:00", propietario: { nombre: "Victoria", apellido: "Cortés" },
  cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 2, cantidadReaperturas: 0, fechaUltimaReapertura: null,
});

const person = (overrides = {}) => {
  const base = {
    idInstitucionUsuario: "r-1", nombre: "Lucía", apellido: "Sosa", correoElectronico: "lucia@example.com", rolInstitucion: "MODERADOR",
    rolesAnteriores: [], estadoRelacion: "ACTIVO", cuentaPendiente: false, invitacionVencida: false, legajoInstitucional: "L-10",
    matriculaProfesional: "MN 123", funcionProfesional: null, fechaInvitacion: "2026-10-01T10:00:00", fechaIncorporacion: "2026-10-03T11:30:00",
    fechaBaja: null, periodos: 1, ...overrides,
  };
  return { ...base, nombreCompleto: [base.nombre, base.apellido].filter(Boolean).join(" ") };
};
const OWNER = person({ idInstitucionUsuario: "r-0", nombre: "Victoria", apellido: "Cortés", rolInstitucion: "PROPIETARIO", correoElectronico: "vic@example.com",
  legajoInstitucional: null, matriculaProfesional: null });
const OPER = person({ idInstitucionUsuario: "r-2", nombre: "Pablo", apellido: "Ríos", rolInstitucion: "OPERADOR", correoElectronico: "pablo@example.com",
  legajoInstitucional: "L-20", matriculaProfesional: null });
const PENDING = person({ idInstitucionUsuario: "r-3", nombre: "Ana", apellido: "Paz", rolInstitucion: "OPERADOR", correoElectronico: "ana@example.com",
  estadoRelacion: "PENDIENTE", cuentaPendiente: true, fechaIncorporacion: null, legajoInstitucional: null, matriculaProfesional: null });
const LEFT = person({ idInstitucionUsuario: "r-4", nombre: "Iván", apellido: "Gil", estadoRelacion: "BAJA", fechaBaja: "2026-10-07T10:00:00",
  correoElectronico: "ivan@example.com", legajoInstitucional: null, matriculaProfesional: null });
const SUMMARY = { totalActivos: 3, moderadoresActivos: 1, operadoresActivos: 1, propietariosActivos: 1, bajas: 1, invitacionesPendientes: 1 };

const page = (items, resumen = SUMMARY) => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 15, resumen });
const NO_ACTIONS = { puedeEditar: false, puedeDesvincular: false, puedeReenviar: false, puedeVerDashboard: false, puedeEliminarDatos: false };
const profile = (overrides = {}) => ({
  ...person(), nombreInstitucion: "Prueba", nombreProfesionalHistorico: null, apellidoProfesionalHistorico: null, origenVinculo: "INVITACION",
  invitadoPor: "Victoria Cortés", fechaVencimientoInvitacion: null, fechaCuentaCreada: "2026-10-02T09:00:00", fechaUltimaModificacion: null,
  periodosAnteriores: [], acciones: NO_ACTIONS, historial: [], ...overrides,
});

// El listado responde según los filtros que llegan en la consulta, como lo hace el backend.
function personnelByQuery(everyone) {
  return (_options, requested) => {
    const url = new URL(requested, "http://x");
    const rol = url.searchParams.get("rol");
    const estado = url.searchParams.get("estado");
    const busqueda = (url.searchParams.get("busqueda") ?? "").toLowerCase();
    const items = everyone.filter((p) => (!rol || p.rolInstitucion === rol) && (!estado || p.estadoRelacion === estado)
      && (!busqueda || [p.nombreCompleto, p.correoElectronico, p.legajoInstitucional, p.matriculaProfesional].some((v) => v && v.toLowerCase().includes(busqueda))));
    return page(items);
  };
}

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(rol, extra = {}) {
  return mockApi({
    "GET /auth/me": jsonResponse(200, INSTITUTIONAL),
    [`GET ${BASE}`]: jsonResponse(200, detail(rol)),
    ...extra,
  });
}

const EVERYONE = [OWNER, person(), OPER, PENDING, LEFT];

describe("Personal: vista general", () => {
  it("muestra a todo el personal, una fila por persona, con pestañas e indicadores del backend", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    renderAt(`/app/instituciones/${ID}/personal`);
    const table = await screen.findByRole("table", { name: "Personal de la institución" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(5);
    expect(within(table).getByText("Victoria Cortés")).toBeInTheDocument();
    expect(within(table).getByText("lucia@example.com")).toBeInTheDocument();
    expect(within(table).getByText("L-10")).toBeInTheDocument();
    expect(within(table).getByText("MN 123")).toBeInTheDocument();
    expect(within(table).getByText("Cuenta pendiente de activación")).toBeInTheDocument();
    expect(within(table).getByText("Dado de baja")).toBeInTheDocument();
    const activeRow = within(table).getByText("Lucía Sosa").closest("tr");
    expect(within(activeRow).getByText("Sin baja")).toBeInTheDocument(); // solo las bajas tienen fecha de baja
    const tabs = screen.getByRole("navigation", { name: "Secciones del personal" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Todos", "Moderadores", "Operadores", "Invitaciones"]);
    expect(within(tabs).getByRole("link", { name: "Todos" })).toHaveClass("is-active");
    expect(within(tabs).getByRole("link", { name: "Todos" })).toHaveAttribute("aria-current", "page"); // NavTabs: la ruta actual se anuncia
    expect(within(tabs).getByRole("link", { name: "Moderadores" })).not.toHaveAttribute("aria-current");
    const kpis = screen.getByLabelText("Indicadores del personal");
    for (const label of ["Integrantes activos", "Moderadores activos", "Operadores activos", "Personal dado de baja", "Invitaciones pendientes"]) {
      expect(within(kpis).getByText(label)).toBeInTheDocument();
    }
    expect(kpis).toHaveTextContent("3");
  });

  it("cada fila lleva data-label para mostrarse como tarjeta en pantallas chicas", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    renderAt(`/app/instituciones/${ID}/personal`);
    const table = await screen.findByRole("table", { name: "Personal de la institución" });
    const labels = Array.from(table.querySelectorAll("tbody tr:first-child [data-label]")).map((cell) => cell.getAttribute("data-label"));
    expect(labels).toEqual(["Persona", "Rol", "Legajo", "Matrícula", "Fecha de incorporación", "Fecha de baja", "Estado"]);
  });

  it("filtra por rol (incluido propietario), por estado y combina filtros", async () => {
    const { calls } = routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal`);
    const table = await screen.findByRole("table", { name: "Personal de la institución" });
    await user.selectOptions(screen.getByLabelText("Rol"), "PROPIETARIO");
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));
    expect(within(screen.getByRole("table")).getByText("Victoria Cortés")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Rol"), "OPERADOR");
    await user.selectOptions(screen.getByLabelText("Estado"), "PENDIENTE");
    await waitFor(() => expect(screen.getByRole("table")).toHaveTextContent("Ana Paz"));
    expect(screen.getByRole("table")).not.toHaveTextContent("Pablo Ríos");
    expect(calls.some((c) => c.url.includes("rol=OPERADOR") && c.url.includes("estado=PENDIENTE"))).toBe(true);
    expect(table).toBeDefined();
  });

  it("el personal dado de baja se ve con el filtro de estado", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("table");
    await user.selectOptions(screen.getByLabelText("Estado"), "BAJA");
    await waitFor(() => expect(screen.getByRole("table")).toHaveTextContent("Iván Gil"));
    const row = within(screen.getByRole("table")).getByText("Iván Gil").closest("tr");
    expect(within(row).getByText("07/10/2026 — 10:00")).toBeInTheDocument(); // fecha de baja
    expect(within(row).getByText("03/10/2026 — 11:30")).toBeInTheDocument(); // fecha de incorporación
    expect(screen.getByRole("table")).not.toHaveTextContent("Pablo Ríos");
  });

  it("busca por nombre, correo, legajo y matrícula y limpia los filtros", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("table");
    expect(screen.queryByRole("button", { name: "Limpiar filtros" })).not.toBeInTheDocument();
    const search = screen.getByLabelText("Buscar");
    for (const [text, expected, absent] of [["pablo", "Pablo Ríos", "Lucía Sosa"], ["ana@example", "Ana Paz", "Pablo Ríos"],
      ["L-20", "Pablo Ríos", "Lucía Sosa"], ["MN 123", "Lucía Sosa", "Pablo Ríos"]]) {
      await user.clear(search);
      await user.type(search, text);
      await waitFor(() => expect(screen.getByRole("table")).toHaveTextContent(expected));
      await waitFor(() => expect(screen.getByRole("table")).not.toHaveTextContent(absent));
    }
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(6));
    expect(search).toHaveValue("");
  });

  it("sin resultados explica que no hay coincidencias y ofrece limpiar", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("table");
    await user.type(screen.getByLabelText("Buscar"), "zzzz");
    expect(await screen.findByText("No hay personal que coincida con los filtros.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeInTheDocument();
  });

  it("las pestañas Moderadores y Operadores piden solo ese rol", async () => {
    const { calls } = routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("table");
    await user.click(screen.getByRole("link", { name: "Operadores" }));
    await waitFor(() => expect(screen.getByRole("table")).toHaveTextContent("Pablo Ríos"));
    expect(screen.getByRole("table")).not.toHaveTextContent("Lucía Sosa");
    expect(screen.queryByLabelText("Rol")).not.toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("rol=OPERADOR"))).toBe(true);
  });

  it("el operador no accede a Personal", async () => {
    const { calls } = routes("OPERADOR", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("link", { name: "Volver a instituciones" }); // lo lleva al panel de la institución
    expect(screen.queryByRole("table", { name: "Personal de la institución" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.key === `GET ${BASE}/personnel`)).toBe(false);
  });

  it("los botones para agregar dependen del permiso: propietario agrega moderadores y moderador, operadores", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    const { unmount } = renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: /moderador/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /operador/i })).not.toBeInTheDocument();
    unmount();
    routes("MODERADOR", { [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE) });
    renderAt(`/app/instituciones/${ID}/personal`);
    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: /operador/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /moderador/i })).not.toBeInTheDocument();
  });
});

describe("Personal: perfil individual", () => {
  const active = profile({
    rolesAnteriores: ["OPERADOR"], fechaUltimaModificacion: "2026-10-09T12:00:00", periodosAnteriores: [
      { idInstitucionUsuario: "r-old", rolInstitucion: "OPERADOR", estadoRelacion: "BAJA", fechaInvitacion: "2026-09-01T10:00:00",
        fechaIncorporacion: "2026-09-02T10:00:00", fechaBaja: "2026-09-20T10:00:00" },
    ],
    historial: [
      { fechaHora: "2026-10-09T12:00:00", tipo: "MODIFICAR_MIEMBRO", titulo: "Datos modificados", descripcion: "Se actualizó el legajo.", resultado: "EXITO",
        realizadoPor: "Victoria Cortés", origen: "AUDITORIA", rolInstitucion: "MODERADOR" },
      { fechaHora: "2026-10-03T11:30:00", tipo: "ACEPTAR_INVITACION", titulo: "Invitación aceptada", descripcion: "Se incorporó como moderador.", resultado: "EXITO",
        realizadoPor: "Lucía Sosa", origen: "AUDITORIA", rolInstitucion: "MODERADOR" },
      { fechaHora: "2026-10-01T10:00:00", tipo: "INVITAR", titulo: "Invitación enviada", descripcion: null, resultado: "EXITO",
        realizadoPor: null, origen: "REGISTRO", rolInstitucion: "MODERADOR" },
    ],
  });

  it("muestra datos personales, profesionales, fechas diferenciadas e historial en orden", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel/r-1`]: jsonResponse(200, active) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    expect(await screen.findByRole("heading", { name: "Lucía Sosa" })).toBeInTheDocument();
    const personal = within(screen.getByRole("heading", { name: "Información personal e institucional" }).closest("section"));
    expect(personal.getByText("lucia@example.com")).toBeInTheDocument();
    expect(personal.getByText("Prueba")).toBeInTheDocument();
    const professional = within(screen.getByRole("heading", { name: "Información profesional" }).closest("section"));
    expect(professional.getByText("MN 123")).toBeInTheDocument();
    expect(professional.getAllByText("Sin informar").length).toBeGreaterThan(0); // función profesional
    const dates = within(screen.getByRole("heading", { name: "Fechas de vinculación" }).closest("section"));
    expect(dates.getByText("01/10/2026 — 10:00")).toBeInTheDocument(); // invitación
    expect(dates.getByText("02/10/2026 — 09:00")).toBeInTheDocument(); // cuenta
    expect(dates.getByText("03/10/2026 — 11:30")).toBeInTheDocument(); // incorporación
    expect(dates.getByText("09/10/2026 — 12:00")).toBeInTheDocument(); // última modificación
    const previous = within(screen.getByRole("list", { name: "Períodos anteriores" }));
    expect(previous.getByText("Operador/a")).toBeInTheDocument();
    const timeline = within(screen.getByRole("list", { name: "Historial institucional" }));
    const titles = timeline.getAllByRole("listitem").map((li) => li.querySelector("b").textContent);
    expect(titles).toEqual(["Datos modificados", "Invitación aceptada", "Invitación enviada"]);
    expect(timeline.getByText(/Responsable no registrado/)).toBeInTheDocument();
    expect(timeline.getByText(/según las fechas del vínculo/)).toBeInTheDocument();
  });

  it("una invitación pendiente dice que la incorporación todavía no ocurrió", async () => {
    routes("MODERADOR", { [`GET ${BASE}/personnel/r-3`]: jsonResponse(200, profile({ ...PENDING, fechaVencimientoInvitacion: "2026-10-15T10:00:00",
      acciones: { puedeEditar: true, puedeDesvincular: true, puedeReenviar: true, puedeVerDashboard: false } })) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-3`);
    const dates = within((await screen.findByRole("heading", { name: "Fechas de vinculación" })).closest("section"));
    expect(dates.getByText("Todavía no ocurrió")).toBeInTheDocument();
    expect(dates.getByText("La invitación vence")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar invitación de Ana Paz" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reenviar invitación a Ana Paz" })).toBeInTheDocument();
  });

  it("una persona dada de baja muestra su baja y no ofrece acciones", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel/r-4`]: jsonResponse(200, profile({ ...LEFT })) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-4`);
    expect(await screen.findByText(/Dado de baja el 07\/10\/2026/)).toBeInTheDocument();
    const dates = within(screen.getByRole("heading", { name: "Fechas de vinculación" }).closest("section"));
    expect(dates.getByText("Fecha de baja")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Desvincular|Editar datos|Reenviar/ })).not.toBeInTheDocument();
  });

  it("elimina a una persona dada de baja solo si acepta el modal; si cancela sigue como Dado de baja", async () => {
    const erasable = profile({ ...LEFT, legajoInstitucional: "L-10", acciones: { ...NO_ACTIONS, puedeEliminarDatos: true } });
    const erased = profile({ ...LEFT, legajoInstitucional: null, datosEliminados: true, acciones: NO_ACTIONS });
    const { calls } = routes("MODERADOR", {
      [`GET ${BASE}/personnel/r-4`]: [jsonResponse(200, erasable), jsonResponse(200, erased)],
      [`DELETE ${BASE}/personnel/r-4/personal-data`]: { ok: true, status: 204, json: async () => null },
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-4`);
    const badge = () => [...document.querySelectorAll(".person-badges .ui-badge")].at(-1); // la última insignia es el estado (la primera es el rol)
    await screen.findByRole("button", { name: "Eliminar a Iván Gil" });
    expect(badge()).toHaveTextContent("Dado de baja");
    await user.click(screen.getByRole("button", { name: "Eliminar a Iván Gil" }));
    const modal = within(screen.getByRole("alertdialog", { name: "¿Eliminar a esta persona?" }));
    expect(modal.getByText(/no se puede deshacer/)).toBeInTheDocument();
    await user.click(modal.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false);
    expect(badge()).toHaveTextContent("Dado de baja");
    await user.click(screen.getByRole("button", { name: "Eliminar a Iván Gil" }));
    await user.click(screen.getByRole("button", { name: "Aceptar y eliminar" }));
    expect(await screen.findByText(/Eliminaste a Iván Gil del personal/)).toBeInTheDocument();
    expect(calls.filter((call) => call.key.startsWith("DELETE"))).toHaveLength(1);
    await waitFor(() => expect(badge()).toHaveTextContent("Eliminado"));
    expect(screen.queryByRole("button", { name: /Eliminar a/ })).not.toBeInTheDocument();
  });

  it("sin permiso sobre ese rol no se ofrece eliminar los datos históricos", async () => {
    routes("MODERADOR", { [`GET ${BASE}/personnel/r-4`]: jsonResponse(200, profile({ ...LEFT, acciones: NO_ACTIONS })) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-4`);
    await screen.findByText(/Dado de baja el 07\/10\/2026/);
    expect(screen.queryByRole("button", { name: /Eliminar a / })).not.toBeInTheDocument();
  });

  it("sin acontecimientos ni datos opcionales lo dice sin inventar", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel/r-1`]: jsonResponse(200, profile({ legajoInstitucional: null, matriculaProfesional: null, fechaCuentaCreada: null })) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    expect(await screen.findByText("Todavía no hay acontecimientos registrados.")).toBeInTheDocument();
    const dates = within(screen.getByRole("heading", { name: "Fechas de vinculación" }).closest("section"));
    expect(dates.getByText("No disponible")).toBeInTheDocument();
    expect(dates.getByText("Todavía no se modificó")).toBeInTheDocument();
  });

  it("un perfil inexistente informa el error y permite volver", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel/r-9`]: jsonResponse(404, { codigo: "MIEMBRO_NO_ENCONTRADO", detail: "x" }) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-9`);
    expect(await screen.findByRole("link", { name: /Volver a Personal/ })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("Personal: navegación", () => {
  it("«Volver a Personal» recupera la pestaña y los filtros de origen", async () => {
    routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: personnelByQuery(EVERYONE),
      [`GET ${BASE}/personnel/r-2`]: jsonResponse(200, profile({ ...OPER })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/operadores`);
    await screen.findByRole("table");
    await user.selectOptions(screen.getByLabelText("Estado"), "ACTIVO");
    await waitFor(() => expect(screen.getByRole("table")).not.toHaveTextContent("Ana Paz"));
    await user.click(screen.getByRole("link", { name: "Ver perfil de Pablo Ríos" }));
    expect(await screen.findByRole("heading", { name: "Pablo Ríos" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Secciones del personal" })).not.toBeInTheDocument();
    const back = screen.getByRole("link", { name: /Volver a Personal/ });
    expect(back).toHaveAttribute("href", `/app/instituciones/${ID}/personal/operadores?estado=ACTIVO`);
    await user.click(back);
    expect(await screen.findByLabelText("Estado")).toHaveValue("ACTIVO");
    expect(screen.getByRole("table")).toHaveTextContent("Pablo Ríos");
  });

  it("las migas del perfil son Personal › Perfil del trabajador y el botón del encabezado vuelve al panel", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel/r-1`]: jsonResponse(200, profile()) });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    await screen.findByRole("heading", { name: "Lucía Sosa" });
    const crumbs = screen.getByRole("navigation", { name: "Ruta de navegación" });
    expect(within(crumbs).getByRole("link", { name: "Personal" })).toBeInTheDocument();
    expect(within(crumbs).getByText("Perfil del trabajador")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Volver al panel" })).toHaveAttribute("href", `/app/instituciones/${ID}`);
  });
});

describe("Personal: invitaciones", () => {
  const invitation = (overrides = {}) => ({
    idInstitucionUsuario: "i-1", nombreCompleto: "Nanami Kento", correoElectronico: "nanami@example.com", rolInstitucion: "OPERADOR",
    estado: "PENDIENTE", cuentaPendiente: true, invitadoPor: "Victoria Cortés", fechaInvitacion: "2026-10-15T19:00:00",
    fechaVencimiento: "2026-10-22T19:00:00", fechaRespuesta: null, puedeReenviar: true, puedeCancelar: true, idPersonal: null, ...overrides,
  });
  const RESUMEN = { PENDIENTE: 1, ACEPTADA: 1, RECHAZADA: 0, CANCELADA: 1, VENCIDA: 0 };
  const listing = (...items) => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 100, resumen: RESUMEN });

  it("muestra cada estado; solo la aceptada enlaza a un perfil de personal y la cancelada no ofrece acciones", async () => {
    routes("MODERADOR", {
      [`GET ${BASE}/invitations`]: listing(
        invitation(),
        invitation({ idInstitucionUsuario: "i-2", nombreCompleto: "Ana Paz", estado: "ACEPTADA", fechaVencimiento: null, fechaRespuesta: "2026-10-16T10:00:00",
          puedeReenviar: false, puedeCancelar: false, idPersonal: "i-2" }),
        invitation({ idInstitucionUsuario: "i-3", nombreCompleto: "Iván Gil", estado: "CANCELADA", fechaVencimiento: null, fechaRespuesta: "2026-10-15T19:47:00",
          puedeReenviar: false, puedeCancelar: false }),
      ),
    });
    renderAt(`/app/instituciones/${ID}/personal/invitaciones`);
    const table = await screen.findByRole("table", { name: "Invitaciones de la institución" });
    expect(within(table).getByText("Pendiente")).toBeInTheDocument();
    expect(within(table).getByText("Aceptada")).toBeInTheDocument();
    expect(within(table).getByText("Cancelada")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Ver perfil de Ana Paz" })).toHaveAttribute("href", `/app/instituciones/${ID}/personal/perfil/i-2`);
    expect(within(table).queryByRole("link", { name: "Ver perfil de Iván Gil" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: /Reenviar invitación a Iván Gil|Cancelar invitación de Iván Gil/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Invitaciones por estado")).toHaveTextContent("Pendiente 1");
    const tabs = screen.getByRole("navigation", { name: "Secciones del personal" });
    expect(within(tabs).getByRole("link", { name: "Invitaciones" })).toHaveClass("is-active");
  });

  it("reenvía y cancela una invitación sin responder, con confirmación, y avisa que no es una desvinculación", async () => {
    const { calls } = routes("MODERADOR", {
      [`GET ${BASE}/invitations`]: [listing(invitation()), listing(invitation()), listing(invitation({ estado: "CANCELADA", puedeReenviar: false, puedeCancelar: false }))],
      [`POST ${BASE}/operators/i-1/resend`]: jsonResponse(200, {}),
      [`DELETE ${BASE}/operators/i-1`]: { ok: true, status: 204, json: async () => null },
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/invitaciones`);
    await user.click(await screen.findByRole("button", { name: "Reenviar invitación a Nanami Kento" }));
    expect(await screen.findByText("Reenviamos la invitación a Nanami Kento.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Cancelar invitación de Nanami Kento" }));
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByText(/Cancelaste la invitación de Nanami Kento. No forma parte del personal./)).toBeInTheDocument();
  });

  it("filtra por estado", async () => {
    const { calls } = routes("PROPIETARIO", { [`GET ${BASE}/invitations`]: (_o, url) => listing(...(url.includes("estado=VENCIDA") ? [invitation({ estado: "VENCIDA" })] : [invitation()])) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/invitaciones`);
    await user.selectOptions(await screen.findByLabelText("Estado"), "VENCIDA");
    await waitFor(() => expect(within(screen.getByRole("table")).getByText("Vencida")).toBeInTheDocument());
    expect(calls.some((call) => call.url.includes("estado=VENCIDA"))).toBe(true);
  });
});

// --- Desvincular a un operador: reasignación obligatoria de sus pacientes ------------------------------------------------------------

const ACTIVE_OPER = profile({ ...OPER, acciones: { puedeEditar: true, puedeDesvincular: true, puedeReenviar: false, puedeVerDashboard: false } });
const PLAN = (overrides = {}) => ({
  idInstitucionUsuario: "r-2", operador: "Pablo Ríos", cantidadPacientes: 2, transferenciasPendientes: 0, bloqueo: null,
  pacientes: [
    { idPerfilMedicion: "p-1", identificadorPseudonimo: "PAC-001", nombre: "Rosa", apellido: "Díaz", transferenciaPendiente: false },
    { idPerfilMedicion: "p-2", identificadorPseudonimo: "PAC-002", nombre: "Luis", apellido: "Paz", transferenciaPendiente: false },
  ],
  destinos: [{ idInstitucionUsuario: "t-1", operador: "Marta Gómez", pacientesActuales: 1 }, { idInstitucionUsuario: "t-2", operador: "Hugo Vera", pacientesActuales: 0 }],
  ...overrides,
});
const offboardRoutes = (plan, extra = {}) => ({
  [`GET ${BASE}/personnel/r-2`]: jsonResponse(200, ACTIVE_OPER),
  [`GET ${BASE}/operators/r-2/offboarding`]: jsonResponse(200, plan),
  ...extra,
});

describe("Desvincular a un operador con pacientes", () => {
  it("pide reasignar antes de desvincular: avisa, cuenta los pacientes, resume y recién al confirmar reasigna y desvincula", async () => {
    const { calls } = routes("MODERADOR", offboardRoutes(PLAN(), {
      [`POST ${BASE}/operators/r-2/offboard`]: jsonResponse(200, { reasignados: 2, destinos: [{ idOperadorNuevo: "t-1", operador: "Marta Gómez", cantidad: 2 }] }),
    }));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Reasignación de pacientes" }));
    expect(dialog.getByText(/Este operador tiene pacientes asignados. Antes de desvincularlo, debés reasignarlos./)).toBeInTheDocument();
    expect(dialog.getByText("2", { selector: "b" })).toBeInTheDocument(); // pacientes pendientes de reasignación
    expect(dialog.getByText("Rosa Díaz")).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith("DELETE") || call.key.endsWith("/offboard"))).toBe(false); // todavía no se desvinculó nada
    expect(dialog.getByRole("button", { name: "Revisar resumen" })).toBeDisabled(); // sin elegir destino no se avanza
    await user.selectOptions(dialog.getByLabelText("Nuevo operador responsable"), "t-1");
    await user.click(dialog.getByRole("button", { name: "Revisar resumen" }));
    expect(dialog.getByText(/pasan a cargo de/)).toHaveTextContent("2 pacientes pasan a cargo de Marta Gómez");
    expect(calls.some((call) => call.key.endsWith("/offboard"))).toBe(false); // el resumen todavía no ejecuta
    await user.click(dialog.getByRole("button", { name: "Confirmar reasignación y desvincular" }));
    await waitFor(() => expect(calls.find((call) => call.key === `POST ${BASE}/operators/r-2/offboard`)).toBeTruthy());
    expect(calls.find((call) => call.key.endsWith("/offboard")).body.asignaciones).toEqual([
      { idPerfilMedicion: "p-1", idOperadorNuevo: "t-1" }, { idPerfilMedicion: "p-2", idOperadorNuevo: "t-1" }]);
    expect(await screen.findByText(/Reasignamos 2 pacientes y Pablo Ríos ya no forma parte de la institución/)).toBeInTheDocument();
  });

  it("permite distribuir los pacientes entre varios operadores y exige elegir uno para cada paciente", async () => {
    const { calls } = routes("PROPIETARIO", offboardRoutes(PLAN(), {
      [`POST ${BASE}/operators/r-2/offboard`]: jsonResponse(200, { reasignados: 2, destinos: [] }),
    }));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Reasignación de pacientes" }));
    await user.click(dialog.getByLabelText("Distribuir entre varios operadores"));
    const selects = dialog.getAllByLabelText("Nuevo responsable");
    await user.selectOptions(selects[0], "t-1");
    expect(dialog.getByRole("button", { name: "Revisar resumen" })).toBeDisabled(); // falta el segundo paciente
    await user.selectOptions(selects[1], "t-2");
    await user.click(dialog.getByRole("button", { name: "Revisar resumen" }));
    expect(dialog.getByText(/Marta Gómez/)).toBeInTheDocument();
    expect(dialog.getByText(/Hugo Vera/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Confirmar reasignación y desvincular" }));
    await waitFor(() => expect(calls.find((call) => call.key.endsWith("/offboard"))).toBeTruthy());
    expect(calls.find((call) => call.key.endsWith("/offboard")).body.asignaciones).toEqual([
      { idPerfilMedicion: "p-1", idOperadorNuevo: "t-1" }, { idPerfilMedicion: "p-2", idOperadorNuevo: "t-2" }]);
  });

  it("cancelar no cambia nada: el operador sigue vinculado", async () => {
    const { calls } = routes("MODERADOR", offboardRoutes(PLAN()));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith("DELETE") || call.key.endsWith("/offboard"))).toBe(false);
    expect(screen.getByRole("button", { name: "Desvincular a Pablo Ríos" })).toBeInTheDocument();
  });

  it("sin otro operador habilitado bloquea la desvinculación e indica qué hacer", async () => {
    routes("MODERADOR", offboardRoutes(PLAN({ destinos: [], bloqueo: "SIN_OPERADOR_DISPONIBLE" })));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/Primero incorporá o habilitá un responsable/)).toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: /Confirmar reasignación/ })).not.toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: "Revisar resumen" })).not.toBeInTheDocument();
  });

  it("con transferencias pendientes de aceptación no se puede confirmar y se marcan los pacientes", async () => {
    const plan = PLAN({ transferenciasPendientes: 1, bloqueo: "TRANSFERENCIAS_PENDIENTES" });
    plan.pacientes[0].transferenciaPendiente = true;
    routes("MODERADOR", offboardRoutes(plan));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/transferencia pendiente de aceptación y siguen a cargo/)).toBeInTheDocument();
    expect(dialog.getByText("Transferencia pendiente")).toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: "Revisar resumen" })).not.toBeInTheDocument();
  });

  it("un operador sin pacientes se desvincula con la confirmación simple", async () => {
    const { calls } = routes("MODERADOR", offboardRoutes(PLAN({ cantidadPacientes: 0, pacientes: [] }), {
      [`DELETE ${BASE}/operators/r-2`]: { ok: true, status: 204, json: async () => null },
    }));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(calls.filter((call) => call.key.startsWith("DELETE"))).toHaveLength(1));
  });

  it("si el servidor rechaza la baja por pacientes asignados, pasa a la reasignación", async () => {
    const { calls } = routes("MODERADOR", offboardRoutes(PLAN({ cantidadPacientes: 0, pacientes: [] }), {
      [`DELETE ${BASE}/operators/r-2`]: jsonResponse(409, { codigo: "PACIENTES_ASIGNADOS", detail: "Este operador tiene 1 paciente asignado." }),
    }));
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    await user.click(await screen.findByRole("button", { name: "Confirmar" }));
    expect(await screen.findByRole("dialog", { name: "Reasignación de pacientes" })).toBeInTheDocument();
    expect(calls.filter((call) => call.key.includes("/offboarding")).length).toBeGreaterThanOrEqual(2); // vuelve a consultar el estado real
  });
});

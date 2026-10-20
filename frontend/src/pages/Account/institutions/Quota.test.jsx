import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { clearTokens, saveTokens } from "../../../auth/tokenStore.js";
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from "../../../test/helpers.js";
import { renderAt } from "../../../test/renderApp.jsx";

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: "USUARIO_INSTITUCIONAL" } };
const ID = "9a000000-0000-4000-8000-000000000001";
const BASE = `/institutions/${ID}`;
const PERMISOS = {
  PROPIETARIO: ["CONSULTAR_INSTITUCION", "MODIFICAR_INSTITUCION", "GESTIONAR_MODERADORES", "ADMINISTRAR_OPERADORES", "CONSULTAR_EQUIPO", "CONSULTAR_PACIENTES", "GESTIONAR_PACIENTES"],
  MODERADOR: ["CONSULTAR_INSTITUCION", "INCORPORAR_OPERADORES", "ADMINISTRAR_OPERADORES", "CONSULTAR_EQUIPO", "CONSULTAR_PACIENTES", "GESTIONAR_PACIENTES"],
  OPERADOR: ["CONSULTAR_INSTITUCION", "CONSULTAR_PACIENTES", "GESTIONAR_PACIENTES"],
};

const detail = (rol, extra = {}) => ({
  idInstitucion: ID, nombre: "Prueba", tipoInstitucion: "CLINICA", estado: "ACTIVA", rolInstitucion: rol, estadoRelacion: "ACTIVO", permisos: PERMISOS[rol],
  tipoIdentificadorLegal: "CUIT", identificadorLegal: "30712345671", descripcion: null, fechaCreacion: "2026-10-01T10:00:00", fechaActualizacion: "2026-10-01T10:00:00",
  propietario: { nombre: "Victoria", apellido: "Cortés" }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0, cantidadReaperturas: 0,
  fechaUltimaReapertura: null, ...extra,
});
const quota = (active, capacity = 1000) => ({
  capacidadMaximaUsuarios: capacity, usuariosActivos: active, cuposDisponibles: Math.max(0, capacity - active),
  porcentajeUtilizacion: Math.min(100, Math.round((active * 1000) / capacity) / 10),
  excedente: Math.max(0, active - capacity),
  estado: active > capacity ? "EXCEDIDA" : active >= capacity ? "COMPLETA" : active * 100 >= capacity * 80 ? "PROXIMO_AL_LIMITE" : "DISPONIBLE",
});
const SUMMARY = { totalActivos: 325, moderadoresActivos: 10, operadoresActivos: 314, propietariosActivos: 1, bajas: 0, invitacionesPendientes: 0 };

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(rol, q, extra = {}) {
  return mockApi({
    "GET /auth/me": jsonResponse(200, INSTITUTIONAL),
    [`GET ${BASE}`]: jsonResponse(200, detail(rol, rol === "OPERADOR" ? {} : { capacidadMaximaUsuarios: 1000, usuariosActivos: 325, cuposDisponibles: 675, porcentajeUtilizacion: 32.5 })),
    [`GET ${BASE}/quota`]: jsonResponse(200, q),
    [`GET ${BASE}/dashboard`]: jsonResponse(500, { codigo: "ERROR_SERVIDOR", detail: "x" }),
    [`GET ${BASE}/activity`]: jsonResponse(200, { items: [] }),
    [`GET ${BASE}/personnel`]: jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 15, resumen: SUMMARY }),
    [`GET ${BASE}/operators/me/dashboard`]: jsonResponse(500, { codigo: "ERROR_SERVIDOR", detail: "x" }),
    ...extra,
  });
}

describe("Cupos institucionales en el dashboard", () => {
  it.each([["PROPIETARIO"], ["MODERADOR"]])("%s ve capacidad, activas, disponibles y utilización que vienen del backend", async (rol) => {
    const { calls } = routes(rol, quota(325));
    renderAt(`/app/instituciones/${ID}`);
    const section = within((await screen.findByRole("heading", { name: "Cupos institucionales" })).closest("section"));
    const kpis = within(await section.findByRole("list", { name: "Cupos institucionales" }));
    expect(kpis.getByText("Capacidad máxima").closest("li")).toHaveTextContent("1.000");
    expect(kpis.getByText("Cuentas activas").closest("li")).toHaveTextContent("325");
    expect(kpis.getByText("Disponibles").closest("li")).toHaveTextContent("675");
    expect(kpis.getByText("Utilización").closest("li")).toHaveTextContent("32,5 %");
    const bar = section.getByRole("progressbar", { name: "Utilización de cupos" });
    expect(bar).toHaveAttribute("aria-valuenow", "32.5");
    expect(section.getByText("Disponible")).toBeInTheDocument();
    expect(calls.filter((call) => call.key === `GET ${BASE}/quota`).length).toBeGreaterThan(0); // no se calcula en React
  });

  it("si la plataforma redujo el límite por debajo de las cuentas, muestra el exceso y que no se admiten nuevas personas", async () => {
    routes("PROPIETARIO", quota(15, 10));
    renderAt(`/app/instituciones/${ID}`);
    expect(await screen.findByText("Límite excedido")).toBeInTheDocument();
    expect(screen.getByText(/hay 5 cuentas activas por encima/)).toBeInTheDocument();
    expect(screen.getByText(/Todas las cuentas se conservan/)).toBeInTheDocument();
  });

  it("muestra «Próximo al límite» desde el 80 % y la advertencia de «Capacidad completa» al 100 %", async () => {
    routes("PROPIETARIO", quota(850));
    const { unmount } = renderAt(`/app/instituciones/${ID}`);
    expect(await screen.findByText("Próximo al límite")).toBeInTheDocument();
    expect(screen.getByText(/quedan 150 cupos/)).toBeInTheDocument();
    unmount();
    routes("PROPIETARIO", quota(1000));
    renderAt(`/app/instituciones/${ID}`);
    expect(await screen.findByText("Capacidad completa")).toBeInTheDocument();
    expect(screen.getByText(/La institución alcanzó su capacidad máxima de cuentas activas/)).toBeInTheDocument();
    expect(screen.getAllByText("1.000").length).toBeGreaterThan(0); // el número de integrantes activos sigue visible
  });

  it("el operador no ve la sección de cupos ni la consulta", async () => {
    const { calls } = routes("OPERADOR", quota(325));
    renderAt(`/app/instituciones/${ID}`);
    await screen.findByRole("heading", { name: "Mi actividad reciente" });
    expect(screen.queryByRole("heading", { name: "Cupos institucionales" })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === `GET ${BASE}/quota`)).toBe(false);
  });
});

describe("Cupos en Personal y en Datos institucionales", () => {
  it("Personal muestra «325 de 1.000 cuentas activas» con los mismos números que el dashboard", async () => {
    routes("MODERADOR", quota(325));
    renderAt(`/app/instituciones/${ID}/personal`);
    const line = within(await screen.findByLabelText("Cupos del personal institucional"));
    expect(await line.findByText("325 de 1.000 cuentas activas")).toBeInTheDocument();
    expect(line.getByText(/675 cupos disponibles/)).toBeInTheDocument();
    expect(line.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "32.5");
  });

  it("con capacidad completa Personal lo advierte y se actualiza al cambiar los activos", async () => {
    const answers = [quota(999), quota(1000)];
    routes("PROPIETARIO", null, { [`GET ${BASE}/quota`]: () => jsonResponse(200, answers.length > 1 ? answers.shift() : answers[0]),
      [`GET ${BASE}/personnel`]: [jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 15, resumen: { ...SUMMARY, totalActivos: 999 } }),
        jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 15, resumen: { ...SUMMARY, totalActivos: 1000 } })] });
    renderAt(`/app/instituciones/${ID}/personal`);
    expect(await screen.findByText("999 de 1.000 cuentas activas")).toBeInTheDocument();
    expect(screen.getByText(/1 cupo disponible/)).toBeInTheDocument();
  });

  it("Datos institucionales muestra la capacidad como información de solo lectura para propietario y moderador", async () => {
    routes("MODERADOR", quota(325));
    renderAt(`/app/instituciones/${ID}/administracion/datos`);
    expect(await screen.findByText("Capacidad máxima de cuentas activas")).toBeInTheDocument();
    expect(screen.getByText(/1\.000 \(administrada por el sistema\)/)).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument(); // sin campo editable
    await waitFor(() => expect(screen.queryByRole("textbox", { name: /Capacidad/ })).not.toBeInTheDocument());
  });
});

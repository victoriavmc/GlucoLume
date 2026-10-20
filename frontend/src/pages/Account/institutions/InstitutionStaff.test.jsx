import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { clearTokens, saveTokens } from "../../../auth/tokenStore.js";
import {
  ACCOUNT,
  TOKENS,
  jsonResponse,
  mockApi,
} from "../../../test/helpers.js";
import { renderAt } from "../../../test/renderApp.jsx";

const INSTITUTIONAL = {
  ...ACCOUNT,
  usuario: { ...ACCOUNT.usuario, tipoCuenta: "USUARIO_INSTITUCIONAL" },
};
const ID = "9a000000-0000-4000-8000-000000000001";
const BASE = `/institutions/${ID}`;
const PATIENTS = [
  "CONSULTAR_PACIENTES",
  "GESTIONAR_PACIENTES",
  "BAJA_PACIENTES",
];
const PERMISOS = {
  PROPIETARIO: [
    "CONSULTAR_INSTITUCION",
    "MODIFICAR_INSTITUCION",
    "GESTIONAR_MODERADORES",
    "ADMINISTRAR_OPERADORES",
    "CONSULTAR_EQUIPO",
    "ELIMINAR_INSTITUCION",
    ...PATIENTS,
  ],
  MODERADOR: [
    "CONSULTAR_INSTITUCION",
    "INCORPORAR_OPERADORES",
    "ADMINISTRAR_OPERADORES",
    "CONSULTAR_EQUIPO",
    ...PATIENTS,
  ],
  OPERADOR: [
    "CONSULTAR_INSTITUCION",
    "CONSULTAR_PACIENTES",
    "GESTIONAR_PACIENTES",
  ],
};
const NO_CONTENT = { ok: true, status: 204, json: async () => null };

function detail(rol = "PROPIETARIO", overrides = {}) {
  return {
    idInstitucion: ID,
    nombre: "Prueba",
    tipoInstitucion: "CLINICA",
    estado: "ACTIVA",
    rolInstitucion: rol,
    estadoRelacion: "ACTIVO",
    permisos: PERMISOS[rol],
    tipoIdentificadorLegal: "CUIT",
    identificadorLegal: "30712345671",
    descripcion: null,
    fechaCreacion: "2026-10-01T10:00:00",
    fechaActualizacion: "2026-10-01T10:00:00",
    propietario: { nombre: "Victoria", apellido: "Cortés" },
    cantidadModeradores: 0,
    cantidadOperadores: 0,
    cantidadPacientes: 2,
    cantidadReaperturas: 0,
    fechaUltimaReapertura: null,
    ...overrides,
  };
}

function member(overrides = {}) {
  return {
    idInstitucionUsuario: "r-1",
    nombre: "Lucía",
    apellido: "Sosa",
    usuario: null,
    correoElectronico: "lucia@example.com",
    rolInstitucion: "MODERADOR",
    estadoRelacion: "PENDIENTE",
    cuentaPendiente: true,
    matriculaProfesional: null,
    fechaInvitacion: "2026-10-08T10:00:00",
    fechaIncorporacion: null,
    fechaBaja: null,
    fechaVencimientoInvitacion: "2026-10-15T10:00:00",
    invitacionVencida: false,
    ...overrides,
  };
}


// Listado unificado del personal (GET /personnel): una fila por persona, con los mismos datos que antes y los nuevos.
function person(overrides = {}) {
  const base = {
    ...member(), rolesAnteriores: [], invitacionVencida: false, legajoInstitucional: null, funcionProfesional: null, periodos: 1,
    ...overrides,
  };
  return { ...base, nombreCompleto: overrides.nombreCompleto ?? [base.nombre, base.apellido].filter(Boolean).join(" ") };
}
const SUMMARY = { totalActivos: 1, moderadoresActivos: 1, operadoresActivos: 0, propietariosActivos: 1, bajas: 0, invitacionesPendientes: 0 };
const NO_ACTIONS = { puedeEditar: false, puedeDesvincular: false, puedeReenviar: false, puedeVerDashboard: false };
function profile(overrides = {}) {
  const merged = {
    ...person(), nombreInstitucion: "Prueba", nombreProfesionalHistorico: null, apellidoProfesionalHistorico: null, origenVinculo: "INVITACION",
    invitadoPor: "Victoriavmc", fechaVencimientoInvitacion: null, fechaCuentaCreada: "2026-10-08T09:55:00", fechaUltimaModificacion: null,
    periodosAnteriores: [], acciones: NO_ACTIONS, historial: [], ...overrides,
  };
  const full = [merged.nombre, merged.apellido].filter(Boolean).join(" ");
  return { ...merged, nombreCompleto: overrides.nombreCompleto ?? full };
}
const personnelPage = (...items) => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 15, resumen: SUMMARY });

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

describe("Moderadores (propietario)", () => {
  it("sin moderadores muestra el mensaje y el botón «Agregar moderador»", async () => {
    routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: personnelPage(),
    });
    renderAt(`/app/instituciones/${ID}/moderadores`);
    expect(
      await screen.findByText(
        "Esta institución todavía no tiene moderadores. Podés agregar uno para que gestione la incorporación de operadores.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Agregar moderador/ }).length,
    ).toBeGreaterThan(0);
  });

  it("persona nueva: nombre, apellido y correo crean la cuenta pendiente y la invitación (sin pacientes)", async () => {
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: [
        personnelPage(),
        personnelPage(person()),
      ],
      [`POST ${BASE}/moderators/lookup`]: jsonResponse(404, {
        codigo: "USUARIO_NO_ENCONTRADO",
        detail: "No existe una cuenta con este correo.",
      }),
      [`POST ${BASE}/moderators`]: jsonResponse(201, member()),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/moderadores`);
    await user.click(
      (await screen.findAllByRole("button", { name: /Agregar moderador/ }))[0],
    );
    const form = screen.getByRole("form", { name: /Agregar moderador/ });
    // Formulario de personal: nada de datos de pacientes.
    expect(
      within(form).queryByLabelText(/DNI|Documento|Fecha de nacimiento|Sexo/),
    ).not.toBeInTheDocument();
    expect(form).toHaveTextContent("Rol: Moderador/a (lo asigna el sistema)");

    await user.type(
      within(form).getByLabelText("Correo electrónico"),
      "lucia@example.com",
    );
    await user.tab();
    expect(
      await within(form).findByText(
        /Se va a crear una cuenta institucional pendiente/,
      ),
    ).toBeInTheDocument();
    await user.click(
      within(form).getByRole("button", { name: "Crear cuenta e invitar" }),
    );
    expect(within(form).getByText("Ingresá el nombre.")).toBeInTheDocument();
    await user.type(within(form).getByLabelText("Nombre profesional"), "Lucía");
    await user.type(within(form).getByLabelText("Apellido profesional"), "Sosa");
    await user.click(
      within(form).getByRole("button", { name: "Crear cuenta e invitar" }),
    );

    expect(
      await screen.findByText(
        /Creamos la cuenta de Lucía Sosa y le enviamos el enlace de activación/,
      ),
    ).toBeInTheDocument();
    // El listado se vuelve a consultar después de crear: se espera a que aparezca la persona.
    expect(
      await screen.findByText("Cuenta pendiente de activación"),
    ).toBeInTheDocument();
    expect(screen.getByText(/lucia@example.com/)).toBeInTheDocument();
    expect(
      calls.find((call) => call.key === `POST ${BASE}/moderators`).body,
    ).toEqual({
      correoElectronico: "lucia@example.com",
      nombre: "Lucía",
      apellido: "Sosa",
      // El nombre profesional arranca con el de la persona.
      nombreProfesionalHistorico: "Lucía",
      apellidoProfesionalHistorico: "Sosa",
    });
    // Nunca se usan los endpoints de pacientes.
    expect(calls.some((call) => call.key.includes("/patients"))).toBe(false);
  });

  it("cuenta institucional existente: se reutiliza sin pedir nombre ni apellido", async () => {
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: [
        personnelPage(),
        personnelPage(
          person({
            cuentaPendiente: false,
            nombre: "Pablo",
            apellido: "Ríos",
            correoElectronico: "pablo@example.com",
          }),
        ),
      ],
      [`POST ${BASE}/moderators/lookup`]: jsonResponse(200, {
        nombre: "Pablo",
        apellido: "Ríos",
        rolPropuesto: "MODERADOR",
        cuentaPendiente: false,
      }),
      [`POST ${BASE}/moderators`]: jsonResponse(
        201,
        member({ cuentaPendiente: false, nombre: "Pablo", apellido: "Ríos" }),
      ),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/moderadores`);
    await user.click(
      (await screen.findAllByRole("button", { name: /Agregar moderador/ }))[0],
    );
    const form = screen.getByRole("form", { name: /Agregar moderador/ });
    await user.type(
      within(form).getByLabelText("Correo electrónico"),
      "pablo@example.com",
    );
    await user.tab();
    expect(
      await within(form).findByText(/Cuenta institucional existente/),
    ).toHaveTextContent("Pablo Ríos");
    expect(within(form).queryByLabelText("Nombre")).not.toBeInTheDocument();
    await user.click(
      within(form).getByRole("button", { name: "Enviar invitación" }),
    );
    expect(
      await screen.findByText(/Invitación enviada a Pablo Ríos/),
    ).toBeInTheDocument();
    expect(
      calls.find((call) => call.key === `POST ${BASE}/moderators`).body,
    ).toEqual({
      correoElectronico: "pablo@example.com",
      // Se toman de la cuenta existente (sus datos globales no se envían ni cambian).
      nombreProfesionalHistorico: "Pablo",
      apellidoProfesionalHistorico: "Ríos",
    });
  });

  it("cuenta individual: se informa y no se envía nada", async () => {
    const message =
      "El correo ingresado no corresponde a una cuenta institucional. Para ser incorporado, el usuario debe contar con una cuenta institucional válida, no personal.";
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: personnelPage(),
      [`POST ${BASE}/moderators/lookup`]: jsonResponse(409, {
        codigo: "CUENTA_PERSONAL_NO_INCORPORABLE",
        detail: message,
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/moderadores`);
    await user.click(
      (await screen.findAllByRole("button", { name: /Agregar moderador/ }))[0],
    );
    const form = screen.getByRole("form", { name: /Agregar moderador/ });
    await user.type(
      within(form).getByLabelText("Correo electrónico"),
      "personal@example.com",
    );
    await user.click(
      within(form).getByRole("button", { name: "Enviar invitación" }),
    );
    expect(await within(form).findByText(message)).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST ${BASE}/moderators`)).toBe(
      false,
    );
  });

  it("reenvía una invitación pendiente y desvincula con confirmación, desde el perfil", async () => {
    const pending = profile({ idInstitucionUsuario: "r-1", acciones: { puedeEditar: true, puedeDesvincular: true, puedeReenviar: true, puedeVerDashboard: false } });
    const active = profile({
      idInstitucionUsuario: "r-2", nombre: "Pablo", apellido: "Ríos", estadoRelacion: "ACTIVO", cuentaPendiente: false,
      fechaIncorporacion: "2026-10-02T09:00:00", fechaVencimientoInvitacion: null, acciones: { puedeEditar: true, puedeDesvincular: true, puedeReenviar: false, puedeVerDashboard: false },
    });
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel/r-1`]: jsonResponse(200, pending),
      [`GET ${BASE}/personnel/r-2`]: jsonResponse(200, active),
      [`POST ${BASE}/moderators/r-1/resend`]: jsonResponse(200, member()),
      [`DELETE ${BASE}/moderators/r-2`]: NO_CONTENT,
    });
    const user = userEvent.setup();
    const { unmount } = renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    await user.click(await screen.findByRole("button", { name: "Reenviar invitación a Lucía Sosa" }));
    expect(await screen.findByText("Reenviamos la invitación a Lucía Sosa.")).toBeInTheDocument();
    unmount();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-2`);
    await user.click(await screen.findByRole("button", { name: "Desvincular a Pablo Ríos" }));
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false); // nada se envía sin confirmar
    await user.click(screen.getByRole("button", { name: /Confirmar/ }));
    expect(await screen.findByText("Pablo Ríos ya no forma parte de la institución.")).toBeInTheDocument();
  });

  it("el personal dado de baja se consulta con el filtro de estado", async () => {
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: () =>
        personnelPage(person({ estadoRelacion: "BAJA", fechaBaja: "2026-10-07T10:00:00", cuentaPendiente: false })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/moderadores`);
    await user.selectOptions(await screen.findByLabelText("Estado"), "BAJA");
    expect((await screen.findAllByText("Dado de baja")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/07\/10\/2026 — 10:00/).length).toBeGreaterThan(0);
    await waitFor(() => expect(calls.some((call) => call.url.includes("estado=BAJA") && call.url.includes("rol=MODERADOR"))).toBe(true));
  });
});

describe("Separación de roles y de pacientes", () => {
  it("los accesos rápidos del propietario llevan a personal, pacientes e inventario según sus permisos", async () => {
    routes("PROPIETARIO");
    renderAt(`/app/instituciones/${ID}`);
    const quick = within(await screen.findByRole("region", { name: "Accesos rápidos" }));
    expect(quick.getByRole("link", { name: /Administrar personal/ })).toHaveAttribute("href", `/app/instituciones/${ID}/personal`);
    expect(quick.getByRole("link", { name: /Administrar paciente/ })).toHaveAttribute("href", `/app/instituciones/${ID}/pacientes`);
    expect(quick.queryByRole("link", { name: /Administrar matrices glucosa/ })).not.toBeInTheDocument(); // sin permiso GESTIONAR_MATRICES
    expect(quick.queryByRole("link", { name: /Agregar/ })).not.toBeInTheDocument();
  });

  it("el propietario supervisa operadores pero no los incorpora", async () => {
    routes("PROPIETARIO", { [`GET ${BASE}/personnel`]: personnelPage() });
    renderAt(`/app/instituciones/${ID}/operadores`);
    expect(
      await screen.findByText(/Los operadores los incorpora un moderador/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Agregar operador/ }),
    ).not.toBeInTheDocument();
  });

  it("el moderador agrega operadores con su formulario de personal", async () => {
    const { calls } = routes("MODERADOR", {
      [`GET ${BASE}/personnel`]: [
        personnelPage(),
        personnelPage(person({ rolInstitucion: "OPERADOR" })),
      ],
      [`POST ${BASE}/operators/lookup`]: jsonResponse(404, {
        codigo: "USUARIO_NO_ENCONTRADO",
        detail: "x",
      }),
      [`POST ${BASE}/operators`]: jsonResponse(
        201,
        member({ rolInstitucion: "OPERADOR" }),
      ),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}`);
    await user.click(
      await screen.findByRole("link", { name: /Administrar personal/ }),
    );
    await user.click(
      (await screen.findAllByRole("button", { name: /Agregar operador/ }))[0],
    );
    const form = screen.getByRole("form", { name: /Agregar operador/ });
    await user.type(
      within(form).getByLabelText("Correo electrónico"),
      "ana@example.com",
    );
    await user.tab();
    await user.type(await within(form).findByLabelText("Nombre profesional"), "Ana");
    await user.type(within(form).getByLabelText("Apellido profesional"), "Paz");
    await user.type(
      within(form).getByLabelText("Matrícula profesional (opcional)"),
      "MP-77",
    );
    await user.type(
      within(form).getByLabelText("Legajo institucional (opcional)"),
      "L-9",
    );
    await user.click(
      within(form).getByRole("button", { name: "Crear cuenta e invitar" }),
    );
    await screen.findByText(/le enviamos el enlace de activación/);
    expect(
      calls.find((call) => call.key === `POST ${BASE}/operators`).body,
    ).toEqual({
      correoElectronico: "ana@example.com",
      nombre: "Ana",
      apellido: "Paz",
      matriculaProfesional: "MP-77",
      legajoInstitucional: "L-9",
      nombreProfesionalHistorico: "Ana",
      apellidoProfesionalHistorico: "Paz",
    });
  });

  it("si el backend rechaza por permisos, se recarga el rol y desaparecen las opciones", async () => {
    routes("MODERADOR", {
      [`GET ${BASE}`]: [
        jsonResponse(200, detail("MODERADOR")),
        jsonResponse(200, detail("OPERADOR")),
      ],
      [`GET ${BASE}/personnel`]: personnelPage(),
      [`POST ${BASE}/operators/lookup`]: jsonResponse(403, {
        codigo: "PERMISO_INSUFICIENTE",
        detail: "Tu rol no lo permite.",
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/operadores`);
    await user.click(
      (await screen.findAllByRole("button", { name: /Agregar operador/ }))[0],
    );
    await user.type(
      screen.getByLabelText("Correo electrónico"),
      "ana@example.com",
    );
    await user.tab();
    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: "Operadores" }),
      ).not.toBeInTheDocument(),
    );
  });
});

describe("Activación de la cuenta invitada", () => {
  it("elige usuario y contraseña, abre la sesión y lleva a aceptar la invitación", async () => {
    window.history.replaceState(null, "", "/activar-cuenta?token=tok-123");
    const { calls } = mockApi({
      "POST /auth/account-activation/check": jsonResponse(200, {
        nombre: "Lucía",
        apellido: "Sosa",
        correoEnmascarado: "lu***@example.com",
        invitaciones: [
          { nombreInstitucion: "Prueba", rolInstitucion: "MODERADOR" },
        ],
      }),
      "POST /auth/account-activation/complete": jsonResponse(200, {
        estado: "AUTENTICADO",
        tokens: TOKENS,
      }),
      "GET /auth/me": jsonResponse(200, INSTITUTIONAL),
      "GET /institutions/mine": jsonResponse(200, []),
      "GET /institutions/invitations": jsonResponse(200, [
        {
          idInstitucionUsuario: "r-1",
          idInstitucion: ID,
          nombreInstitucion: "Prueba",
          tipoInstitucion: "CLINICA",
          rolInstitucion: "MODERADOR",
          nombreInvitante: "Victoria Cortés",
          fechaInvitacion: "2026-10-08T10:00:00",
          fechaVencimiento: "2026-10-15T10:00:00",
          estado: "PENDIENTE",
        },
      ]),
    });
    clearTokens();
    const user = userEvent.setup();
    renderAt("/activar-cuenta?token=tok-123");
    expect(await screen.findByText("Hola, Lucía")).toBeInTheDocument();
    expect(screen.getByText(/moderador\/a de Prueba/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nombre de usuario"), "luciasosa");
    await user.type(
      screen.getByLabelText("Contraseña"),
      "Moderacion#Segura2026",
    );
    await user.type(
      screen.getByLabelText("Repetir contraseña"),
      "Moderacion#Segura2026",
    );
    await user.click(screen.getByRole("checkbox", { name: /Leí la Política de Privacidad/ }));
    await user.click(screen.getByRole("button", { name: /Activar cuenta/ }));
    expect(await screen.findByText(/Activaste tu cuenta/)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", {
        name: "Aceptar invitación de Prueba",
      }),
    ).toBeInTheDocument();
    expect(
      calls.find(
        (call) => call.key === "POST /auth/account-activation/complete",
      ).body,
    ).toEqual({
      token: "tok-123",
      usuario: "luciasosa",
      password: "Moderacion#Segura2026",
      aceptaPoliticaPrivacidad: true,
    });
  });

  it("un enlace inválido o usado se informa", async () => {
    mockApi({
      "POST /auth/account-activation/check": jsonResponse(401, {
        codigo: "TOKEN_INVALIDO",
        detail: "El enlace de activación es inválido o ya fue usado.",
      }),
    });
    clearTokens();
    renderAt("/activar-cuenta?token=viejo");
    expect(
      await screen.findByText(
        "El enlace de activación es inválido o ya fue usado.",
      ),
    ).toBeInTheDocument();
  });
});

describe("Datos administrativos del vínculo", () => {
  it("al agregar un moderador se cargan los cuatro datos; el nombre profesional es editable", async () => {
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel`]: [personnelPage(), personnelPage(person())],
      [`POST ${BASE}/moderators/lookup`]: jsonResponse(404, { codigo: "USUARIO_NO_ENCONTRADO", detail: "x" }),
      [`POST ${BASE}/moderators`]: jsonResponse(201, member()),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/moderadores`);
    await user.click((await screen.findAllByRole("button", { name: /Agregar moderador/ }))[0]);
    const form = screen.getByRole("form", { name: /Agregar moderador/ });
    await user.type(within(form).getByLabelText("Correo electrónico"), "lucia@example.com");
    await user.tab();
    // Sin cuenta: no se muestra dos veces el nombre; el par de «Datos en la institución» es el único.
    expect(within(form).queryByLabelText("Nombre")).not.toBeInTheDocument();
    expect(within(form).queryByLabelText("Apellido")).not.toBeInTheDocument();
    await user.type(await within(form).findByLabelText("Nombre profesional"), "Dra. Lucía");
    await user.type(within(form).getByLabelText("Apellido profesional"), "Sosa");
    await user.type(within(form).getByLabelText("Matrícula profesional (opcional)"), "MN 4521");
    await user.type(within(form).getByLabelText("Legajo institucional (opcional)"), "L-0098");
    await user.click(within(form).getByRole("button", { name: "Crear cuenta e invitar" }));
    await screen.findByText(/le enviamos el enlace de activación/);
    expect(calls.find((call) => call.key === `POST ${BASE}/moderators`).body).toEqual({
      correoElectronico: "lucia@example.com",
      nombre: "Dra. Lucía",
      apellido: "Sosa",
      matriculaProfesional: "MN 4521",
      legajoInstitucional: "L-0098",
      nombreProfesionalHistorico: "Dra. Lucía",
      apellidoProfesionalHistorico: "Sosa",
    });
  });

  it("el propietario ve y edita los datos de un moderador desde su perfil (solo envía lo que cambió)", async () => {
    const active = profile({
      estadoRelacion: "ACTIVO", cuentaPendiente: false, fechaIncorporacion: "2026-10-09T10:00:00", matriculaProfesional: "MN 1",
      legajoInstitucional: "L-1", nombreProfesionalHistorico: "Lucía", apellidoProfesionalHistorico: "Sosa", acciones: { puedeEditar: true, puedeDesvincular: true, puedeReenviar: false, puedeVerDashboard: false },
    });
    const { calls } = routes("PROPIETARIO", {
      [`GET ${BASE}/personnel/r-1`]: [jsonResponse(200, active), jsonResponse(200, { ...active, legajoInstitucional: "L-2" })],
      [`PATCH ${BASE}/moderators/r-1`]: jsonResponse(200, { ...active, legajoInstitucional: "L-2" }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    const professional = within((await screen.findByRole("heading", { name: "Información profesional" })).closest("section"));
    expect(professional.getByText("L-1")).toBeInTheDocument();
    expect(professional.getByText("MN 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Editar datos de Lucía Sosa" }));
    const form = screen.getByRole("form", { name: /Datos de Lucía Sosa/ });
    expect(form).toHaveTextContent("no se modifica desde acá");
    // El único selector es la función profesional: ninguna opción es un rol de permisos.
    const options = within(within(form).getByRole("combobox")).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Sin especificar", "Operador/a", "Enfermero/a", "Médico/a"]);
    expect(options.some((label) => /Propietario|Moderador/.test(label))).toBe(false);
    expect(within(form).getByRole("button", { name: "Guardar cambios" })).toBeDisabled();
    await user.clear(within(form).getByLabelText("Legajo institucional (opcional)"));
    await user.type(within(form).getByLabelText("Legajo institucional (opcional)"), "L-2");
    await user.click(within(form).getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("Guardamos los datos de Lucía Sosa en la institución.")).toBeInTheDocument();
    expect(calls.find((call) => call.key === `PATCH ${BASE}/moderators/r-1`).body).toEqual({ legajoInstitucional: "L-2" });
    expect(await screen.findByText("L-2")).toBeInTheDocument();
  });

  it("un moderador edita los datos de un operador", async () => {
    const operator = profile({ rolInstitucion: "OPERADOR", estadoRelacion: "ACTIVO", cuentaPendiente: false,
      fechaIncorporacion: "2026-10-09T10:00:00", nombre: "Ana", apellido: "Paz", acciones: { puedeEditar: true, puedeDesvincular: true, puedeReenviar: false, puedeVerDashboard: true } });
    const { calls } = routes("MODERADOR", {
      [`GET ${BASE}/personnel/r-1`]: [jsonResponse(200, operator), jsonResponse(200, operator)],
      [`PATCH ${BASE}/operators/r-1`]: jsonResponse(200, { ...operator, matriculaProfesional: "MP 5" }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    await user.click(await screen.findByRole("button", { name: "Editar datos de Ana Paz" }));
    const form = screen.getByRole("form", { name: /Datos de Ana Paz/ });
    await user.type(within(form).getByLabelText("Matrícula profesional (opcional)"), "MP 5");
    await user.click(within(form).getByRole("button", { name: "Guardar cambios" }));
    await screen.findByText("Guardamos los datos de Ana Paz en la institución.");
    expect(calls.find((call) => call.key === `PATCH ${BASE}/operators/r-1`).body).toEqual({ matriculaProfesional: "MP 5" });
  });

  it("un moderador consulta a otros moderadores pero no los edita ni desvincula", async () => {
    routes("MODERADOR", {
      [`GET ${BASE}/personnel/r-1`]: jsonResponse(200, profile({ estadoRelacion: "ACTIVO", cuentaPendiente: false,
        fechaIncorporacion: "2026-10-09T10:00:00" })),
    });
    renderAt(`/app/instituciones/${ID}/personal/perfil/r-1`);
    expect(await screen.findByRole("heading", { name: "Lucía Sosa" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Editar datos|Desvincular/ })).not.toBeInTheDocument();
  });

  it("la función profesional es opcional, ofrece operador, enfermero/a y médico/a, y no habla de permisos", async () => {
    const { calls } = routes("MODERADOR", {
      [`GET ${BASE}/personnel`]: [
        personnelPage(),
        personnelPage(person({ rolInstitucion: "OPERADOR", funcionProfesional: "MEDICO" })),
      ],
      [`POST ${BASE}/operators/lookup`]: jsonResponse(404, { codigo: "USUARIO_NO_ENCONTRADO", detail: "x" }),
      [`POST ${BASE}/operators`]: jsonResponse(201, member({ rolInstitucion: "OPERADOR" })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/operadores`);
    await user.click((await screen.findAllByRole("button", { name: /Agregar operador/ }))[0]);
    const form = screen.getByRole("form", { name: /Agregar operador/ });
    await user.type(within(form).getByLabelText("Correo electrónico"), "ana@example.com");
    await user.tab();
    const select = await within(form).findByLabelText("Rol institucional (opcional)");
    expect(select).toHaveValue("");
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Sin especificar", "Operador/a", "Enfermero/a", "Médico/a",
    ]);
    expect(within(form).getByText(/no cambia sus permisos/)).toBeInTheDocument();
    await user.type(within(form).getByLabelText("Nombre profesional"), "Ana");
    await user.type(within(form).getByLabelText("Apellido profesional"), "Paz");
    await user.selectOptions(select, "MEDICO");
    await user.click(within(form).getByRole("button", { name: "Crear cuenta e invitar" }));
    await screen.findByText(/le enviamos el enlace de activación/);
    expect(calls.find((call) => call.key === `POST ${BASE}/operators`).body).toMatchObject({
      funcionProfesional: "MEDICO", nombre: "Ana", apellido: "Paz",
    });
  });
});

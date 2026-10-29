import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearTokens } from "../../auth/tokenStore.js";
import { jsonResponse, mockApi } from "../../test/helpers.js";
import { renderAt } from "../../test/renderApp.jsx";

beforeEach(() => clearTokens());

describe("Navbar: identidad y logo", () => {
  it("muestra una única identidad GlucoLume y el logo lleva a «Proyecto académico» sin recargar", async () => {
    mockApi({});
    const { container } = renderAt("/");
    const header = container.querySelector("header.navbar");
    expect(within(header).getAllByText(/Gluco/)).toHaveLength(1);
    const nav = screen.getByRole("navigation", { name: "Secciones" });
    expect(within(nav).queryByText("GlucoLume")).not.toBeInTheDocument();

    const logo = within(header).getByRole("link", {
      name: /GlucoLume, ir a Proyecto académico/,
    });
    expect(logo).toHaveAttribute("href", "/#proyecto-academico");
    expect(logo).toHaveTextContent("GlucoLume");
    expect(logo.querySelector("svg")).not.toBeNull(); // ícono + texto en el mismo enlace

    const target = container.querySelector("section#proyecto-academico");
    expect(target).toHaveTextContent(/Proyecto académico/);
    const scrolled = vi.fn();
    target.scrollIntoView = scrolled;
    const user = userEvent.setup();
    await user.click(logo);
    await waitFor(() => expect(scrolled).toHaveBeenCalled());
    expect(window.location.pathname).toBe("/");
  });
});

describe("Landing: estructura", () => {
  it("las secciones aparecen en el orden pedido y el navbar las enlaza", () => {
    mockApi({});
    const { container } = renderAt("/");
    const order = [...container.querySelectorAll("main > section")].map(
      (section) => section.id,
    );
    expect(order).toEqual([
      "proyecto-academico", // hero: destino del logo, no figura en los enlaces
      "que-es",
      "como-funciona",
      "soluciones",
      "contacto",
    ]);

    const nav = screen.getByRole("navigation", { name: "Secciones" });
    const links = within(nav)
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")]);
    expect(links).toEqual([
      ["¿Qué es?", "#que-es"],
      ["Cómo funciona", "#como-funciona"],
      ["Soluciones", "#soluciones"],
      ["Características", "/caracteristicas"],
      ["Contacto", "#contacto"],
      ["Consejos", "/consejos"],
    ]);
  });

  it("las soluciones explican roles reales y llevan al registro con el tipo elegido", () => {
    mockApi({});
    renderAt("/");
    const solutions = screen.getByRole("region", {
      name: "Soluciones de GlucoLume",
    });

    const individual = within(solutions).getByRole("article", {
      name: "Usuario individual",
    });
    expect(
      within(individual).getByText(/No es una herramienta de/),
    ).toBeInTheDocument();
    expect(
      within(individual).getByRole("link", { name: /Crear mi cuenta/ }),
    ).toHaveAttribute("href", "/registro?tipo=usuario");

    const group = within(solutions).getByRole("article", {
      name: "Grupo",
    });
    expect(
      within(group).getByText(
        /manteniendo el control sobre la información personal/,
      ),
    ).toBeInTheDocument();
    for (const role of ["Propietario/a", "Moderador/a", "Integrante"])
      expect(within(group).getByText(role)).toBeInTheDocument();
    expect(
      within(group).getByText(/no da acceso automático/),
    ).toBeInTheDocument();
    expect(
      within(group).getByText(/historial personal de mediciones se conserva/),
    ).toBeInTheDocument();
    expect(
      within(group).getByText(/No es otro tipo de cuenta/),
    ).toBeInTheDocument();

    const institution = within(solutions).getByRole("article", {
      name: "Institución",
    });
    expect(
      within(institution).getByText(
        "¿Por qué una institución usaría GlucoLume?",
      ),
    ).toBeInTheDocument();
    for (const role of ["Propietario/a", "Moderador/a", "Operador/a"]) {
      expect(within(institution).getByText(role)).toBeInTheDocument();
    }
    expect(
      within(institution).getByText(/más de una institución/),
    ).toBeInTheDocument();
    expect(
      within(institution).getByRole("link", {
        name: /Crear cuenta institucional/,
      }),
    ).toHaveAttribute("href", "/registro?tipo=institucion");
  });

  it("características: privacidad, Ley 25.326 y datos anonimizados", () => {
    mockApi({});
    renderAt("/caracteristicas");
    const features = screen.getByRole("region", {
      name: /protegida en cada etapa/,
    });
    expect(within(features).getByText(/Ley N\.º 25\.326/)).toBeInTheDocument();
    for (const title of [
      "Privacidad por diseño",
      "Datos confidenciales",
      "Historial anonimizado",
      "Control de la información",
      "Gestión institucional segura",
      "Retención controlada",
    ]) {
      expect(
        within(features).getByRole("heading", { name: title }),
      ).toBeInTheDocument();
    }
    expect(
      within(features).getByText("Edad al momento de la medición"),
    ).toBeInTheDocument();
    expect(
      within(features).getByText("Correo electrónico"),
    ).toBeInTheDocument();
    expect(within(features).getByText("12 meses")).toBeInTheDocument();
  });
});

describe("Landing: contacto", () => {
  async function fillContact(user) {
    const form = screen.getByRole("region", { name: "¿Querés saber más?" });
    await user.type(within(form).getByLabelText("Nombre"), "Ana Pérez");
    await user.type(
      within(form).getByLabelText("Correo electrónico"),
      "ana@example.com",
    );
    await user.selectOptions(
      within(form).getByLabelText("Tipo de consulta"),
      "INSTITUCIONES",
    );
    await user.type(
      within(form).getByLabelText("Asunto"),
      "Uso en un consultorio",
    );
    await user.type(
      within(form).getByLabelText("Mensaje"),
      "Queremos usarlo en nuestro consultorio.",
    );
    return form;
  }

  it("valida antes de enviar", async () => {
    const { fetchMock } = mockApi({});
    const user = userEvent.setup();
    renderAt("/");
    const form = screen.getByRole("region", { name: "¿Querés saber más?" });
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );
    expect(within(form).getByText("Ingresá tu nombre.")).toBeInTheDocument();
    expect(
      within(form).getByText("Ingresá un correo electrónico válido."),
    ).toBeInTheDocument();
    expect(
      within(form).getByText("Ingresá el asunto de tu consulta."),
    ).toBeInTheDocument();
    expect(within(form).getByText(/Contanos un poco más/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("ofrece los tipos de consulta pedidos", () => {
    mockApi({});
    renderAt("/");
    const select = screen.getByLabelText("Tipo de consulta");
    expect([...select.options].map((option) => option.textContent)).toEqual([
      "Información general",
      "Suscripciones",
      "Ayuda / Soporte",
      "Instituciones",
      "Privacidad y datos",
      "Otro",
    ]);
  });

  it("envía la consulta a POST /contact con los mismos campos que el backend", async () => {
    const { calls } = mockApi({
      "POST /contact": jsonResponse(200, {
        mensaje: "Consulta enviada correctamente.",
        confirmacionEnviada: true,
      }),
    });
    const user = userEvent.setup();
    renderAt("/");
    const form = await fillContact(user);
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );

    const success = await within(form).findByRole("status");
    expect(success).toHaveTextContent("¡Consulta enviada!");
    expect(success).toHaveTextContent(
      "También enviamos una confirmación a tu correo electrónico.",
    );
    expect(calls[0].body).toEqual({
      nombre: "Ana Pérez",
      email: "ana@example.com",
      tipoConsulta: "INSTITUCIONES",
      asunto: "Uso en un consultorio",
      mensaje: "Queremos usarlo en nuestro consultorio.",
      sitioWeb: "",
    });
    expect(within(form).getByLabelText("Mensaje")).toHaveValue("");
  });

  it("no permite doble envío mientras la solicitud está en curso", async () => {
    let release;
    const { calls } = mockApi({
      "POST /contact": () => new Promise((resolve) => (release = resolve)),
    });
    const user = userEvent.setup();
    renderAt("/");
    const form = await fillContact(user);
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );
    const button = within(form).getByRole("button", { name: /Enviando/ });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(calls).toHaveLength(1);
    release(jsonResponse(200, { mensaje: "ok", confirmacionEnviada: true }));
    expect(
      await within(form).findByText(/¡Consulta enviada!/),
    ).toBeInTheDocument();
  });

  it("si la confirmación automática no se envió, el mensaje es genérico pero exitoso", async () => {
    mockApi({
      "POST /contact": jsonResponse(200, {
        mensaje: "ok",
        confirmacionEnviada: false,
      }),
    });
    const user = userEvent.setup();
    renderAt("/");
    const form = await fillContact(user);
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );
    const success = await within(form).findByRole("status");
    expect(success).toHaveTextContent("Recibimos tu consulta correctamente.");
    expect(success).not.toHaveTextContent("confirmación");
    expect(within(form).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("SMTP no disponible: mensaje amigable, sin detalles técnicos", async () => {
    mockApi({
      "POST /contact": jsonResponse(503, {
        codigo: "CORREO_NO_ENVIADO",
        detail: "El formulario de contacto no está disponible en este momento.",
      }),
    });
    const user = userEvent.setup();
    renderAt("/");
    const form = await fillContact(user);
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );
    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "El formulario de contacto no está disponible en este momento.",
    );
  });

  it("errores 422 del backend se muestran en su campo", async () => {
    mockApi({
      "POST /contact": jsonResponse(422, {
        detail: [
          {
            type: "string_too_short",
            loc: ["body", "asunto"],
            msg: "El asunto es demasiado corto.",
          },
        ],
      }),
    });
    const user = userEvent.setup();
    renderAt("/");
    const form = await fillContact(user);
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );
    expect(
      await within(form).findByText("El asunto es demasiado corto."),
    ).toBeInTheDocument();
    expect(within(form).getByLabelText("Asunto")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("muestra el error del backend (por ejemplo, demasiadas consultas)", async () => {
    mockApi({
      "POST /contact": jsonResponse(429, {
        codigo: "DEMASIADAS_SOLICITUDES",
        detail:
          "Enviaste varias consultas seguidas. Probá de nuevo en unos minutos.",
      }),
    });
    const user = userEvent.setup();
    renderAt("/");
    const form = await fillContact(user);
    await user.click(
      within(form).getByRole("button", { name: /Enviar consulta/ }),
    );
    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "Enviaste varias consultas seguidas",
    );
  });
});

// Ordenação e filtro das listas do site. Tudo em cima do DOM já renderizado —
// os dados vêm prontos do gerador, o navegador só reorganiza.

(function () {
  "use strict";

  var COMPARATORS = {
    pos: function (a, b) { return num(a, "pos") - num(b, "pos"); },
    "plays-desc": function (a, b) { return num(b, "plays") - num(a, "plays"); },
    "plays-asc": function (a, b) { return num(a, "plays") - num(b, "plays"); },
    "tracks-desc": function (a, b) { return num(b, "tracks") - num(a, "tracks"); }
  };

  function num(element, name) {
    return parseInt(element.dataset[name] || "0", 10);
  }

  function normalize(text) {
    return (text || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  document.querySelectorAll(".sorts").forEach(function (group) {
    var container = document.querySelector(group.dataset.target);
    if (!container) return;

    group.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button) return;

      var comparator = COMPARATORS[button.dataset.sort];
      var only = button.dataset.only;
      if (!comparator && !only) return;

      group.querySelectorAll("button").forEach(function (other) {
        other.classList.toggle("active", other === button);
      });

      if (comparator) {
        Array.prototype.slice.call(container.children)
          .sort(comparator)
          .forEach(function (child) { container.appendChild(child); });
        return;
      }

      // "Só os inéditos": esconde o que já esteve numa Anuária anterior.
      Array.prototype.forEach.call(container.children, function (child) {
        child.classList.toggle("is-filtered", only === "new" && child.dataset.earlier === "1");
      });
    });
  });

  document.querySelectorAll("input.filter").forEach(function (input) {
    var container = document.querySelector(input.dataset.target);
    if (!container) return;

    input.addEventListener("input", function () {
      var term = normalize(input.value.trim());
      Array.prototype.forEach.call(container.children, function (child) {
        var haystack = child.dataset.search || normalize(child.textContent);
        child.classList.toggle("is-hidden", term !== "" && haystack.indexOf(term) === -1);
      });
    });
  });
})();

// Botão "Atualizar dados": só funciona quando o site está sendo servido pelo
// serve.py (que sabe rodar o atualizar.sh). Em qualquer outro caso (arquivo
// aberto direto, ou servido por um http.server comum), a chamada falha e o
// botão explica o que fazer no terminal.
(function () {
  "use strict";

  var button = document.getElementById("refresh-button");
  if (!button) return;
  var label = button.querySelector(".refresh-label");
  var defaultLabel = label.textContent;

  function setState(text, extraClass) {
    label.textContent = text;
    button.className = "refresh-button" + (extraClass ? " " + extraClass : "");
  }

  button.addEventListener("click", function () {
    if (button.disabled) return;
    button.disabled = true;
    setState("atualizando...", "is-busy");

    fetch("/api/refresh", { method: "POST" })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (result.ok && result.payload.ok) {
          setState("atualizado! recarregando...", "is-done");
          setTimeout(function () { window.location.reload(); }, 700);
          return;
        }
        console.error("Falha ao atualizar:", result.payload);
        setState("falhou — veja o console", "is-error");
        button.disabled = false;
      })
      .catch(function (error) {
        console.error(error);
        setState("sem servidor de atualização — rode: python3 serve.py", "is-error");
        button.disabled = false;
      });
  });
})();

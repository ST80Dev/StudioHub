// Drag&drop ordering per il form di VistaAdempimentoColonne (admin).
// Trasforma la lista di checkbox `id_colonne` in lista riordinabile via
// Sortable.js; tiene sincronizzato il campo nascosto `id_colonne_ordinate`
// con l'ordine corrente (codici dei checkbox spuntati e non).
(function () {
    "use strict";

    function init() {
        var ul = document.querySelector("#id_colonne");
        if (!ul) return;
        var hidden = document.querySelector("#id_colonne_ordinate");
        if (!hidden) return;
        if (typeof Sortable === "undefined") return;

        // I checkbox di Django sono in <ul><li><label><input>...
        ul.querySelectorAll("li").forEach(function (li) {
            li.style.cursor = "move";
            li.style.padding = "2px 4px";
            li.style.borderBottom = "1px dashed #ddd";
        });

        function syncHidden() {
            var ids = [];
            ul.querySelectorAll('li input[type="checkbox"]').forEach(function (inp) {
                // value = codice colonna
                ids.push(inp.value);
            });
            hidden.value = ids.join(",");
        }

        Sortable.create(ul, {
            animation: 120,
            onEnd: syncHidden,
        });

        // Sync iniziale + a ogni toggle (per coprire il caso "spunta nuova colonna":
        // se non e' nell'ordine, finira' in coda al save).
        syncHidden();
        ul.addEventListener("change", syncHidden);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

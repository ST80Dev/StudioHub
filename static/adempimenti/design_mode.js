/* "Modifica vista" per le tabelle adempimenti.
 *
 * Attivato dal partial `_design_mode_toolbar.html`. Permette a staff di:
 *   - riordinare colonne via drag&drop (Sortable.js sulla riga 1 del thead);
 *   - ridimensionare le colonne (handle sul bordo destro di ogni <th>);
 *   - salvare {ordine, larghezze} via POST JSON a `tipo_salva_vista`.
 *
 * Quando l'utente entra in design mode:
 *   - il container con la tabella riceve la classe `sh-design-mode`
 *     (le grip/handle diventano visibili tramite CSS);
 *   - Sortable.js viene inizializzato sulla prima <tr> dello thead,
 *     limitando i drag ai <th> con `data-col-code`;
 *   - ogni drag-end sincronizza la seconda <tr> (filtri) e tutte le righe
 *     della tabella, in modo che il body resti coerente con l'header.
 *
 * Il salvataggio fa POST JSON e poi `location.reload()` per applicare la
 * configurazione lato server (template tags rileggono `column_widths` e
 * l'ordine dal modello). Il messaggio di conferma viene mostrato dal
 * blocco `messages` Django dopo il reload.
 */
(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    function getCsrfToken() {
        const m = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[2]) : "";
    }

    /* Restituisce gli <th> con data-col-code presenti nella prima <tr> del
     * thead — sono le colonne "draggable". */
    function getHeaderColCells(table) {
        const headerRow = table.querySelector("thead tr");
        if (!headerRow) return [];
        return Array.from(headerRow.querySelectorAll("th[data-col-code]"));
    }

    /* Snapshot iniziale per la funzione "Annulla modifiche". */
    function snapshot(table) {
        const cells = getHeaderColCells(table);
        return {
            order: cells.map((c) => c.dataset.colCode),
            widths: cells.reduce((acc, c) => {
                if (c.style.width) {
                    const px = parseInt(c.style.width, 10);
                    if (!Number.isNaN(px)) acc[c.dataset.colCode] = px;
                }
                return acc;
            }, {}),
        };
    }

    /* Riordina TUTTE le righe (thead+tbody+tfoot) basandosi sull'ordine
     * attuale dei <th data-col-code> nella prima <tr> del thead.
     *
     * I `<th>`/`<td>` privi di `data-col-code` (es. checkbox bulk, colonna
     * azioni, le 4 celle Q1..Q4 della vista LIPE-anno) restano nella loro
     * posizione originale.
     */
    function syncRowOrder(table) {
        const headerCells = getHeaderColCells(table);
        const order = headerCells.map((c) => c.dataset.colCode);
        const allRows = table.querySelectorAll("tr");

        allRows.forEach((row, idx) => {
            // Skippa la riga 1 del thead: e' la fonte di verita', gia' ordinata.
            if (row.parentElement.tagName === "THEAD" && row === row.parentElement.firstElementChild) {
                return;
            }
            // Mappa code -> td/th. Le celle senza data-col-code sono "fisse".
            const codeCells = {};
            const fixedCells = [];
            for (const cell of Array.from(row.children)) {
                const code = cell.dataset && cell.dataset.colCode;
                if (code) codeCells[code] = cell;
                else fixedCells.push(cell);
            }
            // Riconosci il pattern: celle fisse possono essere in head o tail.
            // Strategia: rimuovi tutte le celle con code, poi reinserisci
            // nell'ordine target dopo l'ultima cella "fissa di testa".
            const fixedHead = [];
            const fixedTail = [];
            let foundCoded = false;
            for (const cell of Array.from(row.children)) {
                const isCoded = !!(cell.dataset && cell.dataset.colCode);
                if (!isCoded && !foundCoded) fixedHead.push(cell);
                else if (!isCoded && foundCoded) fixedTail.push(cell);
                else if (isCoded) foundCoded = true;
            }

            // Estrai tutte le coded cells.
            order.forEach((code) => {
                const cell = codeCells[code];
                if (!cell) return;
                row.appendChild(cell); // sposta a fondo riga
            });
            // Riporta in coda le fixedTail (che ora sono prima delle coded).
            // Ma le fixedTail sono gia' nel DOM in posizione iniziale; meglio
            // rimuoverle e riaggiungerle in coda.
            fixedTail.forEach((c) => row.appendChild(c));
        });
    }

    /* Inizializza Sortable sulla riga 1 del thead. */
    function initSortable(table, onChange) {
        const row = table.querySelector("thead tr");
        if (!row || !window.Sortable) return null;
        return window.Sortable.create(row, {
            animation: 150,
            draggable: "th[data-col-code]",
            // Limita le aree con cui si puo' afferrare: solo la grip.
            handle: ".sh-col-grip",
            ghostClass: "sh-col-ghost",
            chosenClass: "sh-col-chosen",
            onEnd: function () {
                syncRowOrder(table);
                onChange();
            },
        });
    }

    /* Resize: aggiunge listener mousedown sulle handle. Aggiorna la larghezza
     * inline del <th> mentre si trascina. Imposta minWidth/maxWidth coerenti
     * a quelli del backend (40..800). */
    function initResize(table, onChange) {
        const handles = table.querySelectorAll(".sh-col-resize");
        const MIN = 40;
        const MAX = 800;
        handles.forEach((handle) => {
            handle.addEventListener("mousedown", function (e) {
                e.preventDefault();
                e.stopPropagation();
                const th = handle.closest("th[data-col-code]");
                if (!th) return;
                th.classList.add("sh-resizing");
                const startX = e.clientX;
                const startW = th.getBoundingClientRect().width;

                function onMove(ev) {
                    let w = Math.round(startW + (ev.clientX - startX));
                    if (w < MIN) w = MIN;
                    if (w > MAX) w = MAX;
                    th.style.width = w + "px";
                    th.style.minWidth = w + "px";
                    th.style.maxWidth = w + "px";
                }
                function onUp() {
                    th.classList.remove("sh-resizing");
                    document.removeEventListener("mousemove", onMove);
                    document.removeEventListener("mouseup", onUp);
                    onChange();
                }
                document.addEventListener("mousemove", onMove);
                document.addEventListener("mouseup", onUp);
            });
        });
    }

    /* Applica uno snapshot (ripristina ordine + larghezze). */
    function restoreSnapshot(table, snap) {
        // Rimetti larghezze.
        const cells = getHeaderColCells(table);
        cells.forEach((c) => {
            const w = snap.widths[c.dataset.colCode];
            if (w) {
                c.style.width = w + "px";
                c.style.minWidth = w + "px";
                c.style.maxWidth = w + "px";
            } else {
                c.style.width = "";
                c.style.minWidth = "";
                c.style.maxWidth = "";
            }
        });
        // Rimetti ordine: ricostruisci la riga 1 del thead nell'ordine snap.
        const row = table.querySelector("thead tr");
        if (row) {
            const byCode = {};
            cells.forEach((c) => {
                byCode[c.dataset.colCode] = c;
            });
            snap.order.forEach((code) => {
                const c = byCode[code];
                if (c) row.appendChild(c);
            });
            syncRowOrder(table);
        }
    }

    function setupToolbar(toolbar) {
        const tableSel = toolbar.dataset.tableSelector;
        const table = document.querySelector(tableSel);
        if (!table) return;

        const host = table.closest(".sh-view-host") || table.parentElement;
        const btnToggle = toolbar.querySelector("[data-design-toggle]");
        const labelOff = toolbar.querySelector("[data-label-off]");
        const labelOn = toolbar.querySelector("[data-label-on]");
        const status = toolbar.querySelector("[data-design-status]");
        const dirty = toolbar.querySelector("[data-design-dirty]");
        const btnSave = toolbar.querySelector("[data-design-save]");
        const btnReset = toolbar.querySelector("[data-design-reset]");
        const saveUrl = toolbar.dataset.saveUrl;
        const vista = toolbar.dataset.vista;

        let sortable = null;
        let initialSnap = null;
        let active = false;

        function markDirty() {
            dirty.classList.remove("hidden");
            btnSave.disabled = false;
        }
        function clearDirty() {
            dirty.classList.add("hidden");
            btnSave.disabled = true;
        }

        function enter() {
            active = true;
            host.classList.add("sh-design-mode");
            labelOff.classList.add("hidden");
            labelOn.classList.remove("hidden");
            status.classList.remove("hidden");
            btnSave.classList.remove("hidden");
            btnReset.classList.remove("hidden");
            initialSnap = snapshot(table);
            sortable = initSortable(table, markDirty);
            initResize(table, markDirty);
            clearDirty();
        }

        function exit() {
            active = false;
            host.classList.remove("sh-design-mode");
            labelOff.classList.remove("hidden");
            labelOn.classList.add("hidden");
            status.classList.add("hidden");
            btnSave.classList.add("hidden");
            btnReset.classList.add("hidden");
            if (sortable) {
                sortable.destroy();
                sortable = null;
            }
            // Ripristina se uscito senza salvare.
            if (initialSnap) restoreSnapshot(table, initialSnap);
            clearDirty();
        }

        btnToggle.addEventListener("click", function () {
            if (active) {
                if (!btnSave.disabled) {
                    if (!confirm("Modifiche non salvate. Uscire scartandole?")) return;
                }
                exit();
            } else {
                enter();
            }
        });

        btnReset.addEventListener("click", function () {
            if (initialSnap) restoreSnapshot(table, initialSnap);
            clearDirty();
        });

        btnSave.addEventListener("click", function () {
            const cells = getHeaderColCells(table);
            const colonne = cells.map((c) => c.dataset.colCode);
            const larghezze = {};
            cells.forEach((c) => {
                if (c.style.width) {
                    const px = parseInt(c.style.width, 10);
                    if (!Number.isNaN(px)) larghezze[c.dataset.colCode] = px;
                }
            });
            btnSave.disabled = true;
            btnSave.textContent = "Salvataggio…";
            fetch(saveUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({ vista: vista, colonne: colonne, larghezze: larghezze }),
            })
                .then((r) => r.json().then((d) => ({ ok: r.ok, body: d })))
                .then(({ ok, body }) => {
                    if (ok && body.ok) {
                        // Reload: il blocco messages Django mostrera' conferma.
                        location.reload();
                    } else {
                        alert("Salvataggio fallito: " + (body.error || "errore sconosciuto"));
                        btnSave.disabled = false;
                        btnSave.textContent = "Salva vista per tutti";
                    }
                })
                .catch((err) => {
                    alert("Errore di rete: " + err);
                    btnSave.disabled = false;
                    btnSave.textContent = "Salva vista per tutti";
                });
        });
    }

    ready(function () {
        // Sortable.js e' caricato con `defer` in base.html. Se non e' ancora
        // disponibile (script ordering), aspetta il prossimo tick.
        function go() {
            document.querySelectorAll("[data-design-toolbar]").forEach(setupToolbar);
        }
        if (window.Sortable) go();
        else window.setTimeout(go, 100);
    });
})();

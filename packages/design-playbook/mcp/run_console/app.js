/* Run Console v1 — read-only UI logic (RCV1-007).
   Vanilla JS, no framework, no build step, no storage, no remote
   requests, no service worker. The session token is read once from the
   URL fragment, stripped from history immediately, held only in a
   closure variable, and sent exclusively as an Authorization header.
   Every value from the snapshot is rendered through textContent —
   never as markup. */
"use strict";

(function () {
  var SNAPSHOT_PATH = "/api/v1/snapshot";
  var VIEW_IDS = [
    "loading", "ready", "no-token", "closed", "unsupported",
    "build-error", "error", "network",
  ];
  var CLAMP_LIMIT = 200;

  /* Token lives only in this closure variable: never in the DOM, never
     in a query string, never in storage. */
  var sessionToken = null;
  var firstReadyRender = true;

  /* ---------------------------------------------------------------- */
  /* DOM helpers — the only node factory. Data always lands through    */
  /* textContent / setAttribute, so snapshot strings can never become  */
  /* markup, handlers, or URLs.                                        */
  /* ---------------------------------------------------------------- */

  function el(tag, attrs) {
    var node = document.createElement(tag);
    var children = Array.prototype.slice.call(arguments, 2);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined) return;
        if (key === "class") {
          node.className = value;
        } else if (key === "text") {
          node.textContent = value;
        } else {
          node.setAttribute(key, value);
        }
      });
    }
    children.forEach(function (child) {
      if (child === null || child === undefined) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function view(name) {
    return document.getElementById("view-" + name);
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function showView(name, focusHeading) {
    VIEW_IDS.forEach(function (id) {
      var node = view(id);
      if (node) node.hidden = id !== name;
    });
    var main = document.getElementById("main");
    main.setAttribute("aria-busy", name === "loading" ? "true" : "false");
    /* visibility, not display: the header height never changes. */
    document.getElementById("header-actions").setAttribute(
      "data-hidden", name === "ready" ? "false" : "true"
    );
    if (focusHeading) {
      var heading = view(name).querySelector(".view-heading");
      if (heading) heading.focus();
    }
  }

  function setDetail(id, text) {
    var node = document.getElementById(id);
    if (node) node.textContent = text;
  }

  /* ---------------------------------------------------------------- */
  /* Session token: fragment only, stripped immediately.               */
  /* ---------------------------------------------------------------- */

  function readTokenFromFragment() {
    var match = /^#token=([A-Za-z0-9_-]+)/.exec(window.location.hash);
    if (!match) return null;
    var token = match[1];
    /* The fragment never belongs in history or the address bar. */
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return token;
  }

  /* ---------------------------------------------------------------- */
  /* Authenticated read requests — the only network access.            */
  /* ---------------------------------------------------------------- */

  function requestJson(path) {
    return window.fetch(path, {
      headers: { Authorization: "Bearer " + sessionToken },
      cache: "no-store",
    }).then(function (response) {
      return response.text().then(function (text) {
        var body = null;
        if (text) {
          try { body = JSON.parse(text); } catch (err) { body = null; }
        }
        return { status: response.status, ok: response.ok, body: body };
      });
    });
  }

  function loadSnapshot() {
    showView("loading");
    requestJson(SNAPSHOT_PATH).then(function (result) {
      classifySnapshotResult(result);
    }).catch(function () {
      showView("network", true);
    });
  }

  function classifySnapshotResult(result) {
    if (!result.ok) {
      var error = result.body && result.body.error ? result.body.error : null;
      var code = error ? String(error.code) : "UNKNOWN";
      var message = error ? String(error.message) : "No error detail was provided.";
      if (code === "SESSION_TOKEN_INVALID") {
        setDetail("closed-detail", "The server rejected this session token (" + code + ").");
        showView("closed", true);
      } else if (code === "SNAPSHOT_BUILD_FAILED") {
        setDetail(
          "build-error-detail",
          message + " This error is retryable: reload to request a fresh snapshot build."
        );
        showView("build-error", true);
      } else {
        setDetail("error-detail", "The server answered with error code " + code + ": " + message);
        showView("error", true);
      }
      return;
    }
    var body = result.body;
    if (!body || typeof body !== "object" || typeof body.schemaVersion !== "number") {
      setDetail("error-detail", "The server response was not a recognizable snapshot document.");
      showView("error", true);
      return;
    }
    if (body.schemaVersion !== 1) {
      setDetail(
        "unsupported-detail",
        "The server returned snapshot version " + body.schemaVersion +
          "; this console renders only version 1."
      );
      showView("unsupported", true);
      return;
    }
    var required = ["identity", "intent", "execution", "evaluation", "nextActions", "limitations", "sources"];
    for (var i = 0; i < required.length; i += 1) {
      if (!body[required[i]] || typeof body[required[i]] !== "object") {
        setDetail(
          "error-detail",
          "The snapshot document is missing the section '" + required[i] + "'."
        );
        showView("error", true);
        return;
      }
    }
    renderSnapshot(body);
  }

  /* ---------------------------------------------------------------- */
  /* Assertion rendering — the availability state machine.             */
  /* ---------------------------------------------------------------- */

  function badge(availability) {
    var label = {
      known: "Known",
      unknown: "Unknown",
      stale: "Stale",
      inconsistent: "Inconsistent",
    }[availability] || "Unavailable";
    return el("span", { class: "badge badge-" + availability, text: label });
  }

  function reasonBlock(reason) {
    if (!reason || typeof reason !== "object") {
      return el("p", { class: "reason-block", text: "No reason is recorded." });
    }
    var block = el(
      "p",
      { class: "reason-block" },
      el("span", { class: "reason-code", text: String(reason.code || "unspecified") }),
      " — " + String(reason.message || "No message is recorded.")
    );
    var conflicts = reason.conflicts;
    if (Array.isArray(conflicts) && conflicts.length) {
      var list = el("ul", { class: "conflict-list" });
      conflicts.forEach(function (conflict) {
        list.appendChild(el(
          "li",
          null,
          String(conflict.sourceRef || "source") + ": " + String(conflict.summary || "")
        ));
      });
      block = el("div", { class: "reason-block" }, block, list);
    }
    return block;
  }

  /* Renders one assertion's value area. formatValue turns a known
     result into nodes; stale/inconsistent results are shown too, but
     explicitly marked as stale context, never as current. */
  function assertionNodes(assertion, formatValue) {
    var nodes = [];
    if (!assertion || typeof assertion !== "object") {
      nodes.push(el("p", { class: "empty-note", text: "This assertion is absent from the snapshot." }));
      return nodes;
    }
    var availability = String(assertion.availability || "unknown");
    if (availability === "known") {
      if (assertion.result === null || assertion.result === undefined) {
        nodes.push(el(
          "p",
          { class: "empty-note", text: "Known, but no value is recorded in this snapshot." }
        ));
      } else {
        nodes.push(formatValue(assertion.result));
      }
    } else {
      nodes.push(badge(availability));
      if ((availability === "stale" || availability === "inconsistent") &&
          assertion.result !== null && assertion.result !== undefined) {
        var value = formatValue(assertion.result);
        if (value.classList) value.classList.add("stale-value");
        nodes.push(value);
        nodes.push(el(
          "p",
          { class: "fact-meta", text: "Shown as stale context only — this value must not be read as current." }
        ));
      }
      nodes.push(reasonBlock(assertion.reason));
    }
    return nodes;
  }

  function stringNode(text) {
    return el("p", { class: "fact-value", text: String(text) });
  }

  /* ---------------------------------------------------------------- */
  /* The four comprehension facts, in snapshot order.                   */
  /* ---------------------------------------------------------------- */

  function factCard(index, title, contentNodes, metaNode) {
    var card = el(
      "article",
      { class: "fact", role: "listitem", tabindex: "-1", "data-focusable": "true" },
      el("h3", null, index + ". " + title)
    );
    contentNodes.forEach(function (node) { card.appendChild(node); });
    if (metaNode) card.appendChild(metaNode);
    return card;
  }

  function clampNode(text) {
    var value = String(text);
    var node = el("p", { class: "fact-value", text: value });
    if (value.length > CLAMP_LIMIT) {
      node.classList.add("is-clamped");
      node.setAttribute("title", value);
    }
    return node;
  }

  function renderFacts(snapshot) {
    var grid = document.getElementById("fact-grid");
    clear(grid);

    /* 1 — Intent. */
    var intentNodes = assertionNodes(snapshot.intent.summary, clampNode);
    grid.appendChild(factCard(1, "Intent", intentNodes));

    /* 2 — Verdict. */
    var verdictNodes = assertionNodes(snapshot.evaluation.verdict, function (result) {
      var text = String(result);
      var extra = text === "Pass" ? " badge-verdict-pass" : " badge-verdict-recirculate";
      return el("p", { class: "fact-value" },
        el("span", { class: "badge" + extra, text: text }));
    });
    grid.appendChild(factCard(2, "Verdict", verdictNodes));

    /* 3 — Blocker source / limitation. */
    var blockerNodes = [];
    var blocking = [];
    (snapshot.evaluation.findings || []).forEach(function (finding) {
      if (finding && finding.result && finding.result.disposition === "blocking" &&
          finding.availability === "known") {
        blocking.push(finding);
      }
    });
    if (blocking.length) {
      blockerNodes.push(clampNode(blocking[0].result.issue));
      blockerNodes.push(el(
        "p",
        { class: "fact-meta" },
        blocking.length === 1
          ? "1 blocking finding — see Evaluation for its owner and repair."
          : blocking.length + " blocking findings — see Evaluation for owners and repairs."
      ));
    } else {
      blockerNodes.push(el(
        "p",
        { class: "fact-value", text: "No blocking findings" }
      ));
      var limitationCount = (snapshot.limitations.items || []).length;
      blockerNodes.push(el(
        "p",
        { class: "fact-meta" },
        limitationCount
          ? limitationCount + " recorded limitation" + (limitationCount === 1 ? "" : "s") +
              " — see Limitations."
          : "No limitations recorded."
      ));
    }
    grid.appendChild(factCard(3, "Blocker", blockerNodes));

    /* 4 — Next owner / action. */
    var actionNodes = assertionNodes(snapshot.nextActions.primary, function (result) {
      return clampNode(result.label);
    });
    var primary = snapshot.nextActions.primary;
    if (primary && primary.availability === "known" && primary.result) {
      var owner = primary.result.owner || {};
      var ownerText = "Owner: " + String(owner.actor || "unspecified");
      if (owner.role) ownerText += " (" + String(owner.role) + " role)";
      ownerText += " · kind: " + String(primary.result.kind || "unspecified");
      actionNodes.push(el("p", { class: "fact-meta", text: ownerText }));
    }
    grid.appendChild(factCard(4, "Next action", actionNodes));

    /* First card is the tab stop; arrows roam within the grid. */
    if (grid.children.length) grid.children[0].tabIndex = 0;
  }

  function factGridKeyboard() {
    var grid = document.getElementById("fact-grid");
    grid.addEventListener("keydown", function (event) {
      var cards = Array.prototype.slice.call(grid.children);
      if (!cards.length) return;
      var index = cards.indexOf(document.activeElement);
      var next = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        next = index < 0 ? 0 : (index + 1) % cards.length;
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        next = index < 0 ? cards.length - 1 : (index - 1 + cards.length) % cards.length;
      } else if (event.key === "Home") {
        next = 0;
      } else if (event.key === "End") {
        next = cards.length - 1;
      }
      if (next === null) return;
      event.preventDefault();
      cards.forEach(function (card, i) { card.tabIndex = i === next ? 0 : -1; });
      cards[next].focus();
    });
  }

  /* ---------------------------------------------------------------- */
  /* Detail sections.                                                   */
  /* ---------------------------------------------------------------- */

  function section(id, headingText, children) {
    var sectionNode = el("section", { class: "detail-section", id: id },
      el("h2", null, headingText));
    children.forEach(function (child) { sectionNode.appendChild(child); });
    return sectionNode;
  }

  function kv() {
    /* Alternating term/value arguments: kv("Run id", value, ...). */
    var list = el("dl", { class: "kv" });
    var i;
    for (i = 0; i < arguments.length; i += 2) {
      list.appendChild(el("dt", null, arguments[i]));
      var value = arguments[i + 1];
      if (value === null || value === undefined) {
        list.appendChild(el("dd", { class: "empty-note", text: "—" }));
      } else if (typeof value === "string") {
        list.appendChild(el("dd", { text: value }));
      } else {
        var dd = el("dd");
        dd.appendChild(value);
        list.appendChild(dd);
      }
    }
    return list;
  }

  function emptyNote(text) {
    return el("li", { class: "empty-note", text: text });
  }

  function renderBuildState(snapshot) {
    var banner = document.getElementById("build-state-banner");
    clear(banner);
    var meta = snapshot.identity.snapshot || {};
    var state = String(meta.buildState || "unknown");
    var text = state === "degraded"
      ? "Degraded build — some sources could not be fully read or verified. " +
          "Every value below shows its own availability; nothing is filled in by fallback."
      : "Snapshot is current — all bound sources were read and verified.";
    banner.appendChild(el(
      "p",
      { class: "banner " + (state === "degraded" ? "banner-degraded" : "banner-current"),
        role: "status" },
      el("span", { class: "banner-strong", text: "Build state: " + state + "." }),
      " " + text
    ));
  }

  function renderIdentity(details, snapshot) {
    var identity = snapshot.identity;
    var children = [
      kv("Run id", identity.run && identity.run.result ? identity.run.result.runId : null,
         "Run label", identity.run && identity.run.result ? identity.run.result.label : null),
      kv("Built at", identity.snapshot.builtAt || null,
         "Build state", identity.snapshot.buildState || null,
         "Source set", identity.snapshot.sourceSetHash || null),
    ];
    ["product", "profile"].forEach(function (key) {
      var assertion = identity[key];
      var block = el("div", null, el("h3", null, key === "product" ? "Product" : "Profile"));
      assertionNodes(assertion, function (result) {
        var list = el("dl", { class: "kv" });
        Object.keys(result).forEach(function (field) {
          var value = result[field];
          list.appendChild(el("dt", null, field));
          list.appendChild(el("dd", {
            text: value === null || value === undefined ? "—" : String(value),
          }));
        });
        return list;
      }).forEach(function (node) { block.appendChild(node); });
      children.push(block);
    });
    details.appendChild(section("section-identity", "Identity", children));
  }

  function renderIntent(details, snapshot) {
    var intent = snapshot.intent;
    var children = [];

    var summaryBlock = el("div", null, el("h3", null, "Summary"));
    assertionNodes(intent.summary, function (result) {
      return el("p", { class: "fact-value", text: String(result) });
    }).forEach(function (node) { summaryBlock.appendChild(node); });
    children.push(summaryBlock);

    var criteriaList = el("ul", { class: "plain-list" });
    if (!intent.criteria.length) {
      criteriaList.appendChild(emptyNote("No acceptance criteria are declared in this snapshot."));
    } else {
      intent.criteria.forEach(function (criterion) {
        var item = el("li", null);
        assertionNodes(criterion, function (result) {
          return kv(
            "Criterion", result.criterionId,
            "Title", result.title,
            "Given", result.given,
            "When", result.when,
            "Then", result.then
          );
        }).forEach(function (node) { item.appendChild(node); });
        criteriaList.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, "Acceptance criteria"), criteriaList));

    var contractBlock = el("div", null, el("h3", null, "Contract"));
    assertionNodes(intent.contract, function (result) {
      return kv(
        "Open fields", result.openFields.length ? result.openFields.join(", ") : "none",
        "Assumed fields", result.assumedFields.length ? result.assumedFields.join(", ") : "none",
        "Stale fields", result.staleFields.length ? result.staleFields.join(", ") : "none",
        "Blocking", result.blocking ? "yes — the contract blocks the run" : "no"
      );
    }).forEach(function (node) { contractBlock.appendChild(node); });
    children.push(contractBlock);

    details.appendChild(section("section-intent", "Intent", children));
  }

  function renderExecution(details, snapshot) {
    var execution = snapshot.execution;
    var children = [];

    var progressBlock = el("div", null, el("h3", null, "Progress"));
    assertionNodes(execution.progress, function (result) {
      var list = el("ul", { class: "stage-list" });
      if (!result.observedStages.length) {
        list.appendChild(emptyNote("No stages are observed in this snapshot."));
      } else {
        result.observedStages.forEach(function (stage) {
          var stateClass = stage.presence === "present" ? "stage-state-present" : "";
          var isLatest = result.latestObservedStage !== null &&
            stage.stageId === result.latestObservedStage;
          if (isLatest) stateClass += " stage-state-latest";
          var item = el("li", null,
            el("span", {
              class: "stage-id",
              text: String(stage.stageId) + " (" + String(stage.label) + ")",
            }),
            el("span", {
              class: "stage-state " + stateClass,
              text: String(stage.presence) + (isLatest ? " · latest" : ""),
            })
          );
          if (stage.presence === "skipped" && stage.skipReason) {
            item.appendChild(el("span", {
              class: "stage-skip-reason",
              text: "Skipped: " + String(stage.skipReason),
            }));
          }
          list.appendChild(item);
        });
      }
      return list;
    }).forEach(function (node) { progressBlock.appendChild(node); });
    children.push(progressBlock);

    var previewBlock = el("div", null, el("h3", null, "Preview"));
    assertionNodes(execution.preview, function (result) {
      return kv("State", result.state, "Round", result.round === null ? "—" : String(result.round));
    }).forEach(function (node) { previewBlock.appendChild(node); });
    children.push(previewBlock);

    var repairBlock = el("div", null, el("h3", null, "Repair"));
    assertionNodes(execution.repair, function (result) {
      return kv(
        "Rounds", String(result.rounds),
        "Close reason", result.closeReason === null ? "open" : String(result.closeReason),
        "Waiting for human", result.waitingForHuman ? "yes" : "no",
        "Routes", result.routes.length ? result.routes.join(", ") : "none"
      );
    }).forEach(function (node) { repairBlock.appendChild(node); });
    children.push(repairBlock);

    details.appendChild(section("section-execution", "Execution", children));
  }

  function outcomeNode(outcome) {
    return el("span", {
      class: "outcome outcome-" + String(outcome).toLowerCase(),
      text: String(outcome),
    });
  }

  function renderEvaluation(details, snapshot) {
    var evaluation = snapshot.evaluation;
    var children = [];

    var verdictBlock = el("div", null, el("h3", null, "Verdict"));
    assertionNodes(evaluation.verdict, function (result) {
      return el("p", { class: "fact-value" }, outcomeNode(result));
    }).forEach(function (node) { verdictBlock.appendChild(node); });
    children.push(verdictBlock);

    var criteriaList = el("ul", { class: "plain-list" });
    if (!evaluation.criteria.length) {
      criteriaList.appendChild(emptyNote("No criterion evaluations are recorded in this snapshot."));
    } else {
      evaluation.criteria.forEach(function (criterion) {
        var item = el("li");
        assertionNodes(criterion, function (result) {
          var nodes = [];
          nodes.push(kv(
            "Criterion", result.criterionId,
            "Outcome", outcomeNode(result.outcome),
            "Required proof", result.requiredProof,
            "Observed summary", result.observedSummary
          ));
          if (result.evidenceBindings.length) {
            var bindings = el("ul", { class: "plain-list" });
            result.evidenceBindings.forEach(function (binding) {
              bindings.appendChild(el(
                "li",
                { class: "hash" },
                String(binding.artifactId) + " ← " + String(binding.sourceRef) +
                  " @ " + String(binding.contentHash)
              ));
            });
            nodes.push(el("div", null, el("h3", null, "Evidence"), bindings));
          }
          var wrap = el("div");
          nodes.forEach(function (n) { wrap.appendChild(n); });
          return wrap;
        }).forEach(function (node) { item.appendChild(node); });
        criteriaList.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, "Criterion evaluations"), criteriaList));

    var findingsList = el("ul", { class: "plain-list" });
    if (!evaluation.findings.length) {
      findingsList.appendChild(emptyNote("No findings are recorded in this snapshot."));
    } else {
      evaluation.findings.forEach(function (finding) {
        var item = el("li");
        assertionNodes(finding, function (result) {
          return kv(
            "Finding", result.findingId,
            "Issue", result.issue,
            "Severity", result.severity,
            "Disposition", result.disposition,
            "Owner", result.owner && result.owner.domainId ? String(result.owner.domainId)
              : (result.owner ? String(result.owner.kind) : "unspecified"),
            "Repair", result.repair
          );
        }).forEach(function (node) { item.appendChild(node); });
        findingsList.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, "Findings"), findingsList));

    var coverageBlock = el("div", null, el("h3", null, "Coverage"));
    assertionNodes(evaluation.coverage, function (result) {
      return kv(
        "Declared", String(result.declared),
        "Reviewed", String(result.reviewed),
        "Unreviewed", String(result.unreviewed),
        "Complete", result.complete ? "yes" : "no"
      );
    }).forEach(function (node) { coverageBlock.appendChild(node); });
    children.push(coverageBlock);

    details.appendChild(section("section-evaluation", "Evaluation", children));
  }

  /* ---------------------------------------------------------------- */
  /* Next actions, copy control, and unavailable role/export controls.  */
  /* ---------------------------------------------------------------- */

  function copyPlainText(text, statusNode) {
    function report(ok) {
      statusNode.textContent = ok
        ? "Copied as plain text — nothing is executed."
        : "Copy failed: the browser denied clipboard access.";
    }
    function fallback() {
      var area = el("textarea", { class: "sr-only", readonly: "readonly", tabindex: "-1" });
      area.value = text;
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      area.parentNode.removeChild(area);
      return ok;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { report(true); },
        function () { report(fallback()); }
      );
    } else {
      report(fallback());
    }
  }

  function copyControl(assertion) {
    var known = assertion && assertion.availability === "known" && assertion.result;
    var command = known ? assertion.result.copyableAgentCommand : null;
    var reason;
    if (!assertion || assertion.availability !== "known") {
      reason = "Copy is unavailable: the next action itself is " +
        (assertion ? String(assertion.availability) : "absent") +
        ". No command is synthesized from other values.";
    } else if (typeof command !== "string" || command.length === 0) {
      reason = "Copy is unavailable: this action carries no copyable agent command " +
        "in the snapshot. No command is synthesized from its label.";
    }
    var reasonNode = el("span", {
      class: "unavailable-reason",
      id: "copy-unavailable-reason",
      text: reason,
    });
    if (reason !== undefined) {
      return el("div", null,
        el("button", {
          type: "button",
          class: "button",
          disabled: "disabled",
          "aria-describedby": "copy-unavailable-reason",
        }, "Copy agent command"),
        reasonNode);
    }
    var status = el("span", { class: "copy-status", role: "status", text: "" });
    var button = el("button", { type: "button", class: "button" },
      "Copy agent command (plain text)");
    button.addEventListener("click", function () {
      copyPlainText(command, status);
    });
    return el("div", null, button, status);
  }

  function limitationSummary(items, code) {
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      if (item && item.result && item.result.code === code && item.availability === "known") {
        return String(item.result.summary);
      }
    }
    return null;
  }

  function unavailableControls(items) {
    var roleReason = limitationSummary(items, "role-attestation-owner-unmapped") ||
      "Role attestation is not available in this read-only console phase.";
    var exportReason = limitationSummary(items, "diagnostic-export-contract-unavailable") ||
      "Diagnostic export is not available: its contract is not accepted.";
    return el("div", null,
      el("h3", null, "Unavailable controls"),
      el("div", { class: "action-card" },
        el("button", {
          type: "button", class: "button", disabled: "disabled",
          "aria-describedby": "unavailable-role-reason",
        }, "Attest role"),
        el("span", { class: "unavailable-reason", id: "unavailable-role-reason", text: roleReason })),
      el("div", { class: "action-card" },
        el("button", {
          type: "button", class: "button", disabled: "disabled",
          "aria-describedby": "unavailable-export-reason",
        }, "Export diagnostics"),
        el("span", { class: "unavailable-reason", id: "unavailable-export-reason", text: exportReason })));
  }

  function renderNextActions(details, snapshot) {
    var children = [];

    var primaryBlock = el("div", null, el("h3", null, "Primary action"));
    assertionNodes(snapshot.nextActions.primary, function (result) {
      var owner = result.owner || {};
      var card = el("div", { class: "action-card" },
        el("p", { class: "action-label", text: String(result.label) }),
        el("p", { class: "fact-meta",
          text: "Owner: " + String(owner.actor || "unspecified") +
            (owner.role ? " (" + String(owner.role) + " role)" : "") +
            " · kind: " + String(result.kind || "unspecified") }));
      return card;
    }).forEach(function (node) { primaryBlock.appendChild(node); });
    primaryBlock.appendChild(copyControl(snapshot.nextActions.primary));
    children.push(primaryBlock);

    var alternatives = el("ul", { class: "plain-list" });
    if (!snapshot.nextActions.alternatives.length) {
      alternatives.appendChild(emptyNote("No alternative actions are recorded in this snapshot."));
    } else {
      snapshot.nextActions.alternatives.forEach(function (alternative) {
        var item = el("li");
        assertionNodes(alternative, function (result) {
          var owner = result.owner || {};
          return el("div", { class: "action-card" },
            el("p", { class: "action-label", text: String(result.label) }),
            el("p", { class: "fact-meta",
              text: "Owner: " + String(owner.actor || "unspecified") +
                (owner.role ? " (" + String(owner.role) + " role)" : "") +
                " · kind: " + String(result.kind || "unspecified") }));
        }).forEach(function (node) { item.appendChild(node); });
        alternatives.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, "Alternatives"), alternatives));
    children.push(unavailableControls(snapshot.limitations.items || []));

    details.appendChild(section("section-next-actions", "Next actions", children));
  }

  function renderLimitations(details, snapshot) {
    var list = el("ul", { class: "plain-list" });
    if (!snapshot.limitations.items.length) {
      list.appendChild(emptyNote("No limitations are recorded in this snapshot."));
    } else {
      snapshot.limitations.items.forEach(function (item) {
        var node = el("li");
        assertionNodes(item, function (result) {
          return el("div", null,
            el("p", null,
              el("span", { class: "reason-code", text: String(result.code) }),
              " — " + String(result.summary)),
            result.affectsAssertionIds.length
              ? el("p", { class: "fact-meta",
                  text: "Affects: " + result.affectsAssertionIds.join(", ") })
              : null);
        }).forEach(function (child) { node.appendChild(child); });
        list.appendChild(node);
      });
    }
    details.appendChild(section("section-limitations", "Limitations", [list]));
  }

  /* ---------------------------------------------------------------- */
  /* Sources with on-demand text excerpts.                              */
  /* ---------------------------------------------------------------- */

  function excerptErrorMessage(code) {
    if (code === "SOURCE_HASH_MISMATCH") {
      return "This source changed after the snapshot was built, so the bound excerpt " +
        "is withheld. Reload the snapshot to see the new state.";
    }
    if (code === "SESSION_TOKEN_INVALID") {
      return "The console session has closed; the excerpt cannot be fetched.";
    }
    if (code === "SOURCE_LOCATOR_INVALID") {
      return "The server no longer honors this source locator.";
    }
    return "The excerpt could not be loaded (error code " + String(code) + ").";
  }

  function fetchExcerpt(record, area) {
    area.textContent = "";
    area.appendChild(el("p", {
      class: "excerpt-state",
      text: "Loading excerpt from the console server…",
    }));
    var path = "/api/v1/sources/" + encodeURIComponent(record.locator) +
      "?expectedHash=" + encodeURIComponent(record.verifiedHash);
    requestJson(path).then(function (result) {
      area.textContent = "";
      if (result.status === 200 && result.body && result.body.excerpt !== undefined) {
        area.appendChild(el("p", { class: "excerpt-state" },
          "Excerpt served for " + String(result.body.sourceRef || record.sourceRef) +
            (result.body.truncated ? " — truncated at 4000 characters." : ".")));
        area.appendChild(el("pre", {
          class: "excerpt",
          text: String(result.body.excerpt === null ? "" : result.body.excerpt),
        }));
        return;
      }
      var code = result.body && result.body.error ? result.body.error.code : "UNKNOWN";
      area.appendChild(el("p", { class: "excerpt-state", text: excerptErrorMessage(code) }));
    }).catch(function () {
      area.textContent = "";
      area.appendChild(el("p", {
        class: "excerpt-state",
        text: "The console server is unreachable; the excerpt cannot be fetched.",
      }));
    });
  }

  function renderSources(details, snapshot) {
    var list = el("ul", { class: "plain-list" });
    snapshot.sources.items.forEach(function (record) {
      var excerptable = Boolean(record.locator) && Boolean(record.verifiedHash) &&
        record.readState === "complete";
      if (!excerptable) {
        var reason = !record.locator
          ? "Excerpt unavailable: this source has no server-issued locator."
          : "Excerpt unavailable: readState is '" + String(record.readState) + "'.";
        list.appendChild(el("li", null,
          el("span", { class: "reason-code", text: String(record.sourceRef) }),
          el("p", { class: "unavailable-reason", text: reason })));
        return;
      }
      var area = el("div");
      var detailsNode = el("details", { class: "source" },
        el("summary", null,
          String(record.sourceRef) + " — " + String(record.kind) +
            " · " + String(record.readState) +
            (record.freshness !== "current" ? " · freshness: " + String(record.freshness) : "")),
        el("div", { class: "source-body" },
          kv(
            "Authority", String(record.authorityKey),
            "Observed hash", record.observedHash === null ? null : String(record.observedHash),
            "Verified hash", record.verifiedHash === null ? null : String(record.verifiedHash),
            "Verified at", record.verifiedAt === null ? null : String(record.verifiedAt)
          ),
          area));
      var loaded = false;
      detailsNode.addEventListener("toggle", function () {
        if (detailsNode.open && !loaded) {
          loaded = true;
          fetchExcerpt(record, area);
        }
      });
      list.appendChild(el("li", null, detailsNode));
    });
    details.appendChild(section("section-sources", "Sources", [
      el("p", { class: "section-hint",
        text: "Excerpts are fetched on demand from the console server with the hash " +
          "bound at build time and rendered as plain text." }),
      list,
    ]));
  }

  /* ---------------------------------------------------------------- */
  /* Snapshot rendering entry point.                                    */
  /* ---------------------------------------------------------------- */

  function renderSnapshot(snapshot) {
    renderBuildState(snapshot);

    var runId = snapshot.identity.run && snapshot.identity.run.result
      ? snapshot.identity.run.result.runId : "unknown run";
    document.getElementById("run-id-line").textContent =
      "Run " + String(runId) + " · built " + String(snapshot.identity.snapshot.builtAt || "");

    renderFacts(snapshot);

    var details = document.getElementById("detail-sections");
    clear(details);
    renderIdentity(details, snapshot);
    renderIntent(details, snapshot);
    renderExecution(details, snapshot);
    renderEvaluation(details, snapshot);
    renderNextActions(details, snapshot);
    renderLimitations(details, snapshot);
    renderSources(details, snapshot);

    showView("ready");
    if (firstReadyRender) {
      firstReadyRender = false;
      document.getElementById("main").focus();
    }
  }

  /* ---------------------------------------------------------------- */
  /* Bootstrap.                                                         */
  /* ---------------------------------------------------------------- */

  function init() {
    document.getElementById("reload-button").addEventListener("click", loadSnapshot);
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-reload]"),
      function (button) { button.addEventListener("click", loadSnapshot); }
    );
    factGridKeyboard();
    sessionToken = readTokenFromFragment();
    if (!sessionToken) {
      showView("no-token", true);
      return;
    }
    loadSnapshot();
  }

  init();
})();

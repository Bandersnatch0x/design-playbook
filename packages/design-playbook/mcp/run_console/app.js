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
  /* The single typed action from the closed allowlist (RCV1-009): a full
     snapshot rebuild. The body is the exact closed payload — no fields,
     no variations, no generic command channel. */
  var REFRESH_ACTION_PATH = "/api/v1/actions/refresh";
  var REFRESH_ACTION_BODY = JSON.stringify({ schemaVersion: 1, action: "refresh" });
  var VIEW_IDS = [
    "loading", "ready", "no-token", "closed", "unsupported",
    "build-error", "error", "network",
  ];
  var CLAMP_LIMIT = 200;

  /* Centralized i18n dictionary: complete coverage of zh-CN and en-US */
  var I18N = {
    "en-US": {
      lang_name: "English",
      toggle_target_label: "中文",
      toggle_title: "Switch language (L)",
      skip_link: "Skip to main content",
      app_kicker: "Design Playbook",
      app_title: "Run Console",
      app_subtitle: "Read-only view of one validated run snapshot",
      app_notice: "This console is read-only. It renders the snapshot exactly as built; it never edits run files, never executes commands, and stores nothing — no analytics, no remote requests, no storage.",
      reload_snapshot: "Reload snapshot",
      refresh_snapshot: "Refresh snapshot",
      refresh_title: "Rebuild the snapshot from the run files (R)",
      retry_connection: "Retry connection",
      run_line: "Run {runId} · built {builtAt}",
      unknown_run: "unknown run",

      loading_heading: "Loading run snapshot…",
      loading_sr: "The run snapshot is loading from the local console server.",

      facts_heading: "At a glance",
      facts_hint: "The four facts needed to understand this run, in snapshot order: intent, verdict, blocker, and next owner.",
      facts_aria: "Run comprehension facts: intent, verdict, blocker, next action",
      fact_intent: "Intent",
      fact_verdict: "Verdict",
      fact_blocker: "Blocker",
      fact_next_action: "Next action",

      verdict_pass: "Pass",
      verdict_recirculate: "Recirculate",

      no_blocking_findings: "No blocking findings",
      blocking_singular: "1 blocking finding — see Evaluation for its owner and repair.",
      blocking_plural: "{n} blocking findings — see Evaluation for owners and repairs.",
      limitation_singular: "1 recorded limitation — see Limitations.",
      limitation_plural: "{n} recorded limitations — see Limitations.",
      no_limitations_recorded: "No limitations recorded.",
      owner_prefix: "Owner: {actor}",
      role_suffix: " ({role} role)",
      kind_prefix: " · kind: {kind}",

      avail_known: "Known",
      avail_unknown: "Unknown",
      avail_stale: "Stale",
      avail_inconsistent: "Inconsistent",
      avail_unavailable: "Unavailable",
      stale_context_meta: "Shown as stale context only — this value must not be read as current.",
      assertion_absent: "This assertion is absent from the snapshot.",
      known_no_value: "Known, but no value is recorded in this snapshot.",
      no_reason_recorded: "No reason is recorded.",
      unspecified: "unspecified",
      no_message: "No message is recorded.",

      build_state_degraded: "Degraded build — some sources could not be fully read or verified. Every value below shows its own availability; nothing is filled in by fallback.",
      build_state_current: "Snapshot is current — all bound sources were read and verified.",
      build_state_banner: "Build state: {state}.",

      section_identity: "Identity",
      term_run_id: "Run id",
      term_run_label: "Run label",
      term_built_at: "Built at",
      term_build_state: "Build state",
      term_source_set: "Source set",
      heading_product: "Product",
      heading_profile: "Profile",
      field_name: "name",
      field_version: "version",
      field_declaredTier: "declaredTier",
      field_effectiveTier: "effectiveTier",
      field_confirmedBy: "confirmedBy",
      field_runId: "runId",
      field_label: "label",

      section_intent: "Intent",
      heading_summary: "Summary",
      heading_acceptance_criteria: "Acceptance criteria",
      empty_acceptance_criteria: "No acceptance criteria are declared in this snapshot.",
      term_criterion: "Criterion",
      term_title: "Title",
      term_given: "Given",
      term_when: "When",
      term_then: "Then",
      heading_contract: "Contract",
      term_open_fields: "Open fields",
      term_assumed_fields: "Assumed fields",
      term_stale_fields: "Stale fields",
      term_blocking: "Blocking",
      val_none: "none",
      val_blocking_yes: "yes — the contract blocks the run",
      val_blocking_no: "no",

      section_execution: "Execution",
      heading_progress: "Progress",
      empty_stages: "No stages are observed in this snapshot.",
      stage_latest_badge: " · latest",
      stage_skipped_prefix: "Skipped: ",
      heading_preview: "Preview",
      term_state: "State",
      term_round: "Round",
      heading_repair: "Repair",
      term_rounds: "Rounds",
      term_close_reason: "Close reason",
      val_open: "open",
      term_waiting_for_human: "Waiting for human",
      val_yes: "yes",
      val_no: "no",
      term_routes: "Routes",

      presence_present: "present",
      presence_skipped: "skipped",
      presence_absent: "absent",

      section_evaluation: "Evaluation",
      heading_verdict: "Verdict",
      heading_criterion_evals: "Criterion evaluations",
      empty_criterion_evals: "No criterion evaluations are recorded in this snapshot.",
      term_outcome: "Outcome",
      term_required_proof: "Required proof",
      term_observed_summary: "Observed summary",
      heading_evidence: "Evidence",
      heading_findings: "Findings",
      empty_findings: "No findings are recorded in this snapshot.",
      term_finding: "Finding",
      term_issue: "Issue",
      term_severity: "Severity",
      term_disposition: "Disposition",
      term_owner: "Owner",
      term_repair: "Repair",
      heading_coverage: "Coverage",
      term_declared: "Declared",
      term_reviewed: "Reviewed",
      term_unreviewed: "Unreviewed",
      term_complete: "Complete",

      outcome_pass: "Pass",
      outcome_fail: "Fail",
      outcome_recirculate: "Recirculate",
      outcome_blocked: "Blocked",
      outcome_skipped: "Skipped",

      section_next_actions: "Next actions",
      heading_primary_action: "Primary action",
      heading_alternatives: "Alternatives",
      empty_alternatives: "No alternative actions are recorded in this snapshot.",
      copy_agent_command: "Copy agent command",
      copy_agent_command_plain: "Copy agent command (plain text)",
      copy_success: "Copied as plain text — nothing is executed.",
      copy_failed: "Copy failed: the browser denied clipboard access.",
      copy_unavail_state: "Copy is unavailable: the next action itself is {state}. No command is synthesized from other values.",
      copy_unavail_no_cmd: "Copy is unavailable: this action carries no copyable agent command in the snapshot. No command is synthesized from its label.",
      heading_unavail_controls: "Unavailable controls",
      attest_role: "Attest role",
      export_diagnostics: "Export diagnostics",
      role_reason_default: "Role attestation is not available in this read-only console phase.",
      export_reason_default: "Diagnostic export is not available: its contract is not accepted.",

      section_limitations: "Limitations",
      empty_limitations: "No limitations are recorded in this snapshot.",
      affects_prefix: "Affects: ",
      limitation_diagnostic_export_contract_unavailable: "Diagnostic export is unavailable until its contract is accepted.",
      limitation_role_attestation_owner_unmapped: "Role attestation is unavailable until an existing owner is mapped.",

      section_sources: "Sources",
      sources_hint: "Excerpts are fetched on demand from the console server with the hash bound at build time and rendered as plain text.",
      source_summary_line: "{sourceRef} — {kind} · {readState}",
      freshness_suffix: " · freshness: {freshness}",
      term_authority: "Authority",
      term_observed_hash: "Observed hash",
      term_verified_hash: "Verified hash",
      term_verified_at: "Verified at",
      kind_authority_record: "authority-record",
      kind_artifact: "artifact",
      kind_package: "package",
      kind_session_selection: "session-selection",
      readState_complete: "complete",
      readState_missing: "missing",
      readState_error: "error",
      freshness_current: "current",
      freshness_stale: "stale",
      source_unavail_no_locator: "Excerpt unavailable: this source has no server-issued locator.",
      source_unavail_read_state: "Excerpt unavailable: readState is '{readState}'.",
      excerpt_loading: "Loading excerpt from the console server…",
      excerpt_served_for: "Excerpt served for {sourceRef}{truncated}.",
      truncated_text: " — truncated at 4000 characters",
      excerpt_err_hash_mismatch: "This source changed after the snapshot was built, so the bound excerpt is withheld. Reload the snapshot to see the new state.",
      excerpt_err_closed: "The console session has closed; the excerpt cannot be fetched.",
      excerpt_err_locator: "The server no longer honors this source locator.",
      excerpt_err_generic: "The excerpt could not be loaded (error code {code}).",
      excerpt_err_unreachable: "The console server is unreachable; the excerpt cannot be fetched.",

      err_no_token_title: "No session token",
      err_no_token_p2: "The token travels only in the URL fragment, is removed from the address bar and history immediately after load, and is used solely for the Authorization header of this page’s requests. It is never stored.",

      err_closed_title: "Session closed",
      err_closed_p1: "The session token is invalid or the console session has closed. Start the console again with the launcher and open the fresh URL it prints.",
      err_closed_detail: "The server rejected this session token ({code}).",

      err_unsupported_title: "Unsupported snapshot version",
      err_unsupported_detail: "The server returned snapshot version {version}; this console renders only version 1.",
      err_unsupported_p2: "This console renders only Snapshot v1. No partial or fallback rendering is attempted for other versions.",

      err_build_title: "Snapshot could not be built",
      err_build_p1: "The console server failed to build a valid snapshot for this run. No previous snapshot is shown in its place.",
      err_build_detail_suffix: " This error is retryable: reload to request a fresh snapshot build.",

      err_error_title: "The snapshot could not be loaded",
      err_error_code_msg: "The server answered with error code {code}: {message}",
      err_error_not_snapshot: "The server response was not a recognizable snapshot document.",
      err_error_missing_section: "The snapshot document is missing the section '{section}'.",

      err_network_title: "Console server unreachable",
      err_network_p1: "The local console server did not answer. It may have stopped — restart it with the launcher and reopen the URL it prints.",
    },
    "zh-CN": {
      lang_name: "中文",
      toggle_target_label: "English",
      toggle_title: "切换语言 (L)",
      skip_link: "跳转到主要内容",
      app_kicker: "设计手册",
      app_title: "运行控制台",
      app_subtitle: "单次验证运行快照的只读视图",
      app_notice: "本控制台为纯只读视图。它严格按构建时原样呈现快照；绝不修改运行文件，绝不执行任何命令，且不存储任何内容 — 无数据统计、无远程请求、无本地存储。",
      reload_snapshot: "重新加载快照",
      refresh_snapshot: "刷新快照",
      refresh_title: "从运行文件重建快照 (R)",
      retry_connection: "重试连接",
      run_line: "运行 {runId} · 构建于 {builtAt}",
      unknown_run: "未知运行",

      loading_heading: "正在加载运行快照…",
      loading_sr: "正在从本地控制台服务加载运行快照。",

      facts_heading: "运行概览",
      facts_hint: "理解本次运行所需的四个核心事实（按快照顺序）：意图、结论、阻塞项和下一动作。",
      facts_aria: "运行理解核心事实：意图、结论、阻塞项、下一动作",
      fact_intent: "意图",
      fact_verdict: "结论",
      fact_blocker: "阻塞项",
      fact_next_action: "下一动作",

      verdict_pass: "Pass",
      verdict_recirculate: "Recirculate",

      no_blocking_findings: "无阻塞性发现",
      blocking_singular: "1 条阻塞性发现 — 请参阅「评估」查看责任人与修复建议。",
      blocking_plural: "{n} 条阻塞性发现 — 请参阅「评估」查看责任人与修复建议。",
      limitation_singular: "1 条记录的局限性 — 请参阅「局限性」。",
      limitation_plural: "{n} 条记录的局限性 — 请参阅「局限性」。",
      no_limitations_recorded: "未记录局限性。",
      owner_prefix: "责任方: {actor}",
      role_suffix: " ({role} 角色)",
      kind_prefix: " · 类型: {kind}",

      avail_known: "已知",
      avail_unknown: "未知",
      avail_stale: "已过期",
      avail_inconsistent: "不一致",
      avail_unavailable: "不可用",
      stale_context_meta: "仅作为过期上下文展示 — 该值不可作为当前有效状态读取。",
      assertion_absent: "此断言在快照中缺失。",
      known_no_value: "状态已知，但本次快照未记录具体值。",
      no_reason_recorded: "未记录原因。",
      unspecified: "未指定",
      no_message: "未记录消息。",

      build_state_degraded: "降级构建 — 部分源未能完整读取或验证。下方各字段均展示其自身可用性；绝不通过降级备选值填补。",
      build_state_current: "快照为最新状态 — 所有绑定的源均已成功读取并验证。",
      build_state_banner: "构建状态: {state}。",

      section_identity: "身份标识",
      term_run_id: "运行 ID",
      term_run_label: "运行标签",
      term_built_at: "构建时间",
      term_build_state: "构建状态",
      term_source_set: "源集哈希",
      heading_product: "产品信息",
      heading_profile: "运行配置",
      field_name: "名称 (name)",
      field_version: "版本 (version)",
      field_declaredTier: "声明层级 (declaredTier)",
      field_effectiveTier: "有效层级 (effectiveTier)",
      field_confirmedBy: "确认人 (confirmedBy)",
      field_runId: "运行编号 (runId)",
      field_label: "标签 (label)",

      section_intent: "意图",
      heading_summary: "意图摘要",
      heading_acceptance_criteria: "验收标准列表",
      empty_acceptance_criteria: "本次快照中未声明验收标准。",
      term_criterion: "标准编号",
      term_title: "标题",
      term_given: "前提 (Given)",
      term_when: "触发 (When)",
      term_then: "预期 (Then)",
      heading_contract: "运行契约",
      term_open_fields: "待定字段",
      term_assumed_fields: "假设字段",
      term_stale_fields: "过期字段",
      term_blocking: "是否阻塞",
      val_none: "无",
      val_blocking_yes: "是 — 该契约阻塞运行",
      val_blocking_no: "否",

      section_execution: "执行",
      heading_progress: "阶段执行进度",
      empty_stages: "本次快照中未观测到任何阶段。",
      stage_latest_badge: " · 最新",
      stage_skipped_prefix: "已跳过: ",
      heading_preview: "预览状态",
      term_state: "状态",
      term_round: "轮次",
      heading_repair: "修复记录",
      term_rounds: "轮次数",
      term_close_reason: "关闭原因",
      val_open: "开启",
      term_waiting_for_human: "等待人工介入",
      val_yes: "是",
      val_no: "否",
      term_routes: "路由",

      presence_present: "已执行 (present)",
      presence_skipped: "已跳过 (skipped)",
      presence_absent: "未执行 (absent)",

      section_evaluation: "评估",
      heading_verdict: "最终结论",
      heading_criterion_evals: "逐项验收评估",
      empty_criterion_evals: "本次快照中未记录标准评估。",
      term_outcome: "评估结果",
      term_required_proof: "所需证明",
      term_observed_summary: "观测摘要",
      heading_evidence: "证据链绑定",
      heading_findings: "问题发现",
      empty_findings: "本次快照中未记录任何问题发现。",
      term_finding: "发现编号",
      term_issue: "问题描述",
      term_severity: "严重程度",
      term_disposition: "处置建议",
      term_owner: "责任人",
      term_repair: "修复动作",
      heading_coverage: "覆盖率统计",
      term_declared: "已声明标准数",
      term_reviewed: "已评审数",
      term_unreviewed: "未评审数",
      term_complete: "是否完备覆盖",

      outcome_pass: "通过 (Pass)",
      outcome_fail: "未通过 (Fail)",
      outcome_recirculate: "重新流转 (Recirculate)",
      outcome_blocked: "阻塞 (Blocked)",
      outcome_skipped: "跳过 (Skipped)",

      section_next_actions: "后续动作",
      heading_primary_action: "主要动作",
      heading_alternatives: "备选动作",
      empty_alternatives: "本次快照中未记录备选动作。",
      copy_agent_command: "复制智能体指令",
      copy_agent_command_plain: "复制智能体指令 (纯文本)",
      copy_success: "已复制为纯文本 — 绝不执行任何操作。",
      copy_failed: "复制失败：浏览器拒绝了剪贴板访问权限。",
      copy_unavail_state: "复制不可用：下一动作本身为 {state}。绝不通过其他值合成指令。",
      copy_unavail_no_cmd: "复制不可用：本次快照中该动作未携带可复制的智能体指令。绝不根据标签名称合成指令。",
      heading_unavail_controls: "不可用控件",
      attest_role: "认证角色",
      export_diagnostics: "导出诊断报告",
      role_reason_default: "在当前只读控制台阶段，角色认证不可用。",
      export_reason_default: "诊断导出不可用：未接受其契约。",

      section_limitations: "局限性",
      empty_limitations: "本次快照中未记录任何局限性。",
      affects_prefix: "影响范围: ",
      limitation_diagnostic_export_contract_unavailable: "诊断导出不可用：未接受其契约。",
      limitation_role_attestation_owner_unmapped: "角色认证不可用：尚未映射责任人。",

      section_sources: "源数据",
      sources_hint: "代码或文档摘录按需从控制台服务获取，并绑定构建时哈希以纯文本形式安全渲染。",
      source_summary_line: "{sourceRef} — {kind} · {readState}",
      freshness_suffix: " · 新鲜度: {freshness}",
      term_authority: "权威方",
      term_observed_hash: "观测哈希",
      term_verified_hash: "验证哈希",
      term_verified_at: "验证时间",
      kind_authority_record: "权威记录 (authority-record)",
      kind_artifact: "生成产物 (artifact)",
      kind_package: "软件包 (package)",
      kind_session_selection: "会话选择 (session-selection)",
      readState_complete: "完整 (complete)",
      readState_missing: "缺失 (missing)",
      readState_error: "错误 (error)",
      freshness_current: "最新 (current)",
      freshness_stale: "已过期 (stale)",
      source_unavail_no_locator: "摘录不可用：该源没有服务端分配的定位符。",
      source_unavail_read_state: "摘录不可用：读取状态为 '{readState}'。",
      excerpt_loading: "正在从控制台服务加载摘录…",
      excerpt_served_for: "已获取 {sourceRef} 的摘录{truncated}。",
      truncated_text: " — 已在 4000 字符处截断",
      excerpt_err_hash_mismatch: "此源在快照构建后发生了更改，因此拒绝提供绑定的摘录内容。请重新加载快照以查看最新状态。",
      excerpt_err_closed: "控制台会话已关闭；无法获取摘录。",
      excerpt_err_locator: "服务端不再支持此源定位符。",
      excerpt_err_generic: "无法加载摘录（错误代码 {code}）。",
      excerpt_err_unreachable: "控制台服务不可达；无法获取摘录。",

      err_no_token_title: "无会话令牌",
      err_no_token_p2: "令牌仅通过 URL 片段传递，在加载后立即从地址栏和历史记录中移除，且仅用于本页面请求的 Authorization 头。绝不会持久化存储。",

      err_closed_title: "会话已关闭",
      err_closed_p1: "会话令牌无效或控制台会话已关闭。请使用启动器重新启动控制台，并打开其打印的新 URL。",
      err_closed_detail: "服务端拒绝了此会话令牌 ({code})。",

      err_unsupported_title: "不支持的快照版本",
      err_unsupported_detail: "服务端返回了快照版本 {version}；本控制台仅支持渲染版本 1。",
      err_unsupported_p2: "本控制台仅渲染 Snapshot v1。对于其他版本，不会尝试任何部分渲染或备选渲染。",

      err_build_title: "无法构建快照",
      err_build_p1: "控制台服务未能为本次运行构建有效快照。绝不使用先前的快照替代展示。",
      err_build_detail_suffix: " 此错误可重试：重新加载以请求全新的快照构建。",

      err_error_title: "快照加载失败",
      err_error_code_msg: "服务端返回错误代码 {code}: {message}",
      err_error_not_snapshot: "服务端响应不是可识别的快照文档。",
      err_error_missing_section: "快照文档缺少 '{section}' 小节。",

      err_network_title: "控制台服务不可达",
      err_network_p1: "本地控制台服务未响应。服务可能已停止 — 请通过启动器重新启动并打开其打印的 URL。",
    },
  };

  /* Token and language state live ONLY in memory: never in the DOM,
     never in storage APIs, never in cookies. Default language is en-US. */
  var sessionToken = null;
  var currentLang = "en-US";
  var lastSnapshot = null;
  var lastError = null;
  var firstReadyRender = true;

  function t(key, params) {
    var dict = I18N[currentLang] || I18N["en-US"];
    var str = dict[key] !== undefined ? dict[key] : (I18N["en-US"][key] !== undefined ? I18N["en-US"][key] : key);
    if (params && typeof params === "object") {
      Object.keys(params).forEach(function (param) {
        str = str.replace(new RegExp("\\{" + param + "\\}", "g"), String(params[param]));
      });
    }
    return str;
  }

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
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function showView(name, focusHeading) {
    VIEW_IDS.forEach(function (id) {
      var node = view(id);
      if (node) node.hidden = id !== name;
    });
    var main = document.getElementById("main");
    if (main) main.setAttribute("aria-busy", name === "loading" ? "true" : "false");
    /* visibility, not display: the header height never changes. */
    var headerActions = document.getElementById("header-actions");
    if (headerActions) {
      headerActions.setAttribute("data-hidden", name === "ready" ? "false" : "true");
    }
    if (focusHeading) {
      var targetView = view(name);
      if (targetView) {
        var heading = targetView.querySelector(".view-heading");
        if (heading) heading.focus();
      }
    }
  }

  function setDetail(id, text) {
    var node = document.getElementById(id);
    if (node) node.textContent = text;
  }

  function updateStaticTexts() {
    var d = I18N[currentLang] || I18N["en-US"];
    var skip = document.getElementById("skip-link");
    if (skip) skip.textContent = d.skip_link;
    var kicker = document.getElementById("app-kicker");
    if (kicker) kicker.textContent = d.app_kicker;
    var title = document.querySelector("h1") || document.getElementById("app-title");
    if (title) title.textContent = d.app_title;
    var subtitle = document.getElementById("app-subtitle");
    if (subtitle) subtitle.textContent = d.app_subtitle;
    var notice = document.getElementById("app-notice");
    if (notice) notice.textContent = d.app_notice;
    var reloadBtn = document.getElementById("reload-button");
    if (reloadBtn) reloadBtn.textContent = d.reload_snapshot;
    var refreshBtn = document.getElementById("refresh-button");
    if (refreshBtn) {
      refreshBtn.setAttribute("title", d.refresh_title);
      var refreshLabel = document.getElementById("refresh-button-label");
      if (refreshLabel) refreshLabel.textContent = d.refresh_snapshot;
    }
    var langBtn = document.getElementById("lang-toggle-button");
    if (langBtn) {
      langBtn.setAttribute("title", d.toggle_title);
      var label = document.getElementById("lang-toggle-label");
      if (label) label.textContent = d.toggle_target_label;
    }
    var loadHead = document.getElementById("loading-heading");
    if (loadHead) loadHead.textContent = d.loading_heading;
    var loadSr = document.getElementById("loading-sr");
    if (loadSr) loadSr.textContent = d.loading_sr;
    var factsHead = document.getElementById("facts-heading");
    if (factsHead) factsHead.textContent = d.facts_heading;
    var factsHint = document.getElementById("facts-hint");
    if (factsHint) factsHint.textContent = d.facts_hint;
    var factGrid = document.getElementById("fact-grid");
    if (factGrid) factGrid.setAttribute("aria-label", d.facts_aria);

    var noTokenHead = document.getElementById("no-token-heading");
    if (noTokenHead) noTokenHead.textContent = d.err_no_token_title;
    var noTokenP1 = document.getElementById("no-token-p1");
    if (noTokenP1) {
      clear(noTokenP1);
      if (currentLang === "zh-CN") {
        noTokenP1.appendChild(document.createTextNode("打开此页面时未携带会话令牌。请使用启动器打印的完整 URL 打开控制台 — 它指向相同的主机与端口，并以 "));
        noTokenP1.appendChild(el("code", null, "/#token=TOKEN"));
        noTokenP1.appendChild(document.createTextNode(" 结尾。"));
      } else {
        noTokenP1.appendChild(document.createTextNode("This page was opened without a session token. Open the console with the exact URL printed by the launcher — it points at this same host and port and ends with "));
        noTokenP1.appendChild(el("code", null, "/#token=TOKEN"));
        noTokenP1.appendChild(document.createTextNode("."));
      }
    }
    var noTokenP2 = document.getElementById("no-token-p2");
    if (noTokenP2) noTokenP2.textContent = d.err_no_token_p2;

    var closedHead = document.getElementById("closed-heading");
    if (closedHead) closedHead.textContent = d.err_closed_title;
    var closedP1 = document.getElementById("closed-p1");
    if (closedP1) closedP1.textContent = d.err_closed_p1;

    var unsuppHead = document.getElementById("unsupported-heading");
    if (unsuppHead) unsuppHead.textContent = d.err_unsupported_title;
    var unsuppP2 = document.getElementById("unsupported-p2");
    if (unsuppP2) unsuppP2.textContent = d.err_unsupported_p2;

    var buildHead = document.getElementById("build-error-heading");
    if (buildHead) buildHead.textContent = d.err_build_title;
    var buildP1 = document.getElementById("build-error-p1");
    if (buildP1) buildP1.textContent = d.err_build_p1;
    var buildReload = document.getElementById("build-error-reload-btn");
    if (buildReload) buildReload.textContent = d.reload_snapshot;

    var errHead = document.getElementById("error-heading");
    if (errHead) errHead.textContent = d.err_error_title;
    var errReload = document.getElementById("generic-error-reload-btn");
    if (errReload) errReload.textContent = d.reload_snapshot;

    var netHead = document.getElementById("network-heading");
    if (netHead) netHead.textContent = d.err_network_title;
    var netP1 = document.getElementById("network-p1");
    if (netP1) netP1.textContent = d.err_network_p1;
    var netRetry = document.getElementById("network-retry-btn");
    if (netRetry) netRetry.textContent = d.retry_connection;

    document.title = currentLang === "zh-CN"
      ? "运行控制台 — 只读运行快照"
      : "Run Console — read-only run snapshot";
  }

  function renderLastError() {
    if (!lastError) return;
    if (lastError.type === "closed") {
      setDetail("closed-detail", t("err_closed_detail", { code: lastError.code }));
      showView("closed");
    } else if (lastError.type === "build-error") {
      setDetail("build-error-detail", lastError.message + t("err_build_detail_suffix"));
      showView("build-error");
    } else if (lastError.type === "unsupported") {
      setDetail("unsupported-detail", t("err_unsupported_detail", { version: lastError.version }));
      showView("unsupported");
    } else if (lastError.type === "error") {
      if (lastError.subType === "not_snapshot") {
        setDetail("error-detail", t("err_error_not_snapshot"));
      } else if (lastError.subType === "missing_section") {
        setDetail("error-detail", t("err_error_missing_section", { section: lastError.section }));
      } else {
        setDetail("error-detail", t("err_error_code_msg", { code: lastError.code, message: lastError.message }));
      }
      showView("error");
    } else if (lastError.type === "network") {
      showView("network");
    }
  }

  function toggleLanguage() {
    currentLang = currentLang === "en-US" ? "zh-CN" : "en-US";
    document.documentElement.setAttribute("lang", currentLang === "zh-CN" ? "zh-CN" : "en");
    updateStaticTexts();
    if (lastSnapshot) {
      renderSnapshot(lastSnapshot);
    } else if (lastError) {
      renderLastError();
    }
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
  /* Authenticated read requests — the only network access, plus the  */
  /* one typed action POST from the closed allowlist (RCV1-009).      */
  /* ---------------------------------------------------------------- */

  function parseJsonResponse(response) {
    return response.text().then(function (text) {
      var body = null;
      if (text) {
        try { body = JSON.parse(text); } catch (err) { body = null; }
      }
      return { status: response.status, ok: response.ok, body: body };
    });
  }

  function requestJson(path) {
    return window.fetch(path, {
      headers: { Authorization: "Bearer " + sessionToken },
      cache: "no-store",
    }).then(parseJsonResponse);
  }

  /* The refresh action: same-origin POST of the exact closed payload.
     Nothing else about the request varies, so no other command can be
     smuggled through this path. */
  function requestRefreshAction() {
    return window.fetch(REFRESH_ACTION_PATH, {
      method: "POST",
      headers: {
        Authorization: "Bearer " + sessionToken,
        "Content-Type": "application/json",
      },
      body: REFRESH_ACTION_BODY,
      cache: "no-store",
    }).then(parseJsonResponse);
  }

  function loadSnapshot() {
    showView("loading");
    requestJson(SNAPSHOT_PATH).then(function (result) {
      classifySnapshotResult(result);
    }).catch(function () {
      lastError = { type: "network" };
      showView("network", true);
    });
  }

  /* A full rebuild on the server. The response is a complete snapshot
     document (or the typed error envelope), so the same classification
     applies — a failed rebuild shows the build-error view and never the
     previous snapshot as current. */
  function refreshSnapshot() {
    if (!sessionToken) return;
    showView("loading");
    requestRefreshAction().then(function (result) {
      classifySnapshotResult(result);
    }).catch(function () {
      lastError = { type: "network" };
      showView("network", true);
    });
  }

  function classifySnapshotResult(result) {
    if (!result.ok) {
      var error = result.body && result.body.error ? result.body.error : null;
      var code = error ? String(error.code) : "UNKNOWN";
      var message = error ? String(error.message) : "No error detail was provided.";
      if (code === "SESSION_TOKEN_INVALID") {
        lastError = { type: "closed", code: code };
        setDetail("closed-detail", t("err_closed_detail", { code: code }));
        showView("closed", true);
      } else if (code === "SNAPSHOT_BUILD_FAILED") {
        lastError = { type: "build-error", message: message };
        setDetail("build-error-detail", message + t("err_build_detail_suffix"));
        showView("build-error", true);
      } else {
        lastError = { type: "error", code: code, message: message };
        setDetail("error-detail", t("err_error_code_msg", { code: code, message: message }));
        showView("error", true);
      }
      return;
    }
    var body = result.body;
    if (!body || typeof body !== "object" || typeof body.schemaVersion !== "number") {
      lastError = { type: "error", subType: "not_snapshot" };
      setDetail("error-detail", t("err_error_not_snapshot"));
      showView("error", true);
      return;
    }
    if (body.schemaVersion !== 1) {
      lastError = { type: "unsupported", version: body.schemaVersion };
      setDetail("unsupported-detail", t("err_unsupported_detail", { version: body.schemaVersion }));
      showView("unsupported", true);
      return;
    }
    var required = ["identity", "intent", "execution", "evaluation", "nextActions", "limitations", "sources"];
    for (var i = 0; i < required.length; i += 1) {
      if (!body[required[i]] || typeof body[required[i]] !== "object") {
        lastError = { type: "error", subType: "missing_section", section: required[i] };
        setDetail("error-detail", t("err_error_missing_section", { section: required[i] }));
        showView("error", true);
        return;
      }
    }
    lastError = null;
    lastSnapshot = body;
    renderSnapshot(body);
  }

  /* ---------------------------------------------------------------- */
  /* Assertion rendering — the availability state machine.             */
  /* ---------------------------------------------------------------- */

  function badge(availability) {
    var key = "avail_" + String(availability);
    var label = t(key) || String(availability);
    return el("span", { class: "badge badge-" + availability, text: label });
  }

  function reasonBlock(reason) {
    if (!reason || typeof reason !== "object") {
      return el("p", { class: "reason-block", text: t("no_reason_recorded") });
    }
    var block = el(
      "p",
      { class: "reason-block" },
      el("span", { class: "reason-code", text: String(reason.code || t("unspecified")) }),
      " — " + String(reason.message || t("no_message"))
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
      nodes.push(el("p", { class: "empty-note", text: t("assertion_absent") }));
      return nodes;
    }
    var availability = String(assertion.availability || "unknown");
    if (availability === "known") {
      if (assertion.result === null || assertion.result === undefined) {
        nodes.push(el(
          "p",
          { class: "empty-note", text: t("known_no_value") }
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
          { class: "fact-meta", text: t("stale_context_meta") }
        ));
      }
      nodes.push(reasonBlock(assertion.reason));
    }
    return nodes;
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
    grid.appendChild(factCard(1, t("fact_intent"), intentNodes));

    /* 2 — Verdict. */
    var verdictNodes = assertionNodes(snapshot.evaluation.verdict, function (result) {
      var text = String(result);
      var extra = text === "Pass" ? " badge-verdict-pass" : " badge-verdict-recirculate";
      var label = text === "Pass" ? t("verdict_pass") : (text === "Recirculate" ? t("verdict_recirculate") : text);
      return el("p", { class: "fact-value" },
        el("span", { class: "badge" + extra, text: label }));
    });
    grid.appendChild(factCard(2, t("fact_verdict"), verdictNodes));

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
          ? t("blocking_singular")
          : t("blocking_plural", { n: blocking.length })
      ));
    } else {
      blockerNodes.push(el(
        "p",
        { class: "fact-value", text: t("no_blocking_findings") }
      ));
      var limitationCount = (snapshot.limitations.items || []).length;
      blockerNodes.push(el(
        "p",
        { class: "fact-meta" },
        limitationCount
          ? (limitationCount === 1
              ? t("limitation_singular")
              : t("limitation_plural", { n: limitationCount }))
          : t("no_limitations_recorded")
      ));
    }
    grid.appendChild(factCard(3, t("fact_blocker"), blockerNodes));

    /* 4 — Next owner / action. */
    var actionNodes = assertionNodes(snapshot.nextActions.primary, function (result) {
      return clampNode(result.label);
    });
    var primary = snapshot.nextActions.primary;
    if (primary && primary.availability === "known" && primary.result) {
      var owner = primary.result.owner || {};
      var ownerActor = String(owner.actor || t("unspecified"));
      var ownerText = t("owner_prefix", { actor: ownerActor });
      if (owner.role) {
        ownerText += t("role_suffix", { role: String(owner.role) });
      }
      ownerText += t("kind_prefix", { kind: String(primary.result.kind || t("unspecified")) });
      actionNodes.push(el("p", { class: "fact-meta", text: ownerText }));
    }
    grid.appendChild(factCard(4, t("fact_next_action"), actionNodes));

    /* First card is the tab stop; arrows roam within the grid. */
    if (grid.children.length) grid.children[0].tabIndex = 0;
  }

  function factGridKeyboard() {
    var grid = document.getElementById("fact-grid");
    if (!grid) return;
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
      ? t("build_state_degraded")
      : t("build_state_current");
    banner.appendChild(el(
      "p",
      { class: "banner " + (state === "degraded" ? "banner-degraded" : "banner-current"),
        role: "status" },
      el("span", { class: "banner-strong", text: t("build_state_banner", { state: state }) }),
      " " + text
    ));
  }

  function renderIdentity(details, snapshot) {
    var identity = snapshot.identity;
    var children = [
      kv(t("term_run_id"), identity.run && identity.run.result ? identity.run.result.runId : null,
         t("term_run_label"), identity.run && identity.run.result ? identity.run.result.label : null),
      kv(t("term_built_at"), identity.snapshot.builtAt || null,
         t("term_build_state"), identity.snapshot.buildState || null,
         t("term_source_set"), identity.snapshot.sourceSetHash || null),
    ];
    var subRow = el("div", { class: "sub-cards-row" });
    ["product", "profile"].forEach(function (key) {
      var assertion = identity[key];
      var heading = key === "product" ? t("heading_product") : t("heading_profile");
      var block = el("div", null, el("h3", null, heading));
      assertionNodes(assertion, function (result) {
        var list = el("dl", { class: "kv" });
        Object.keys(result).forEach(function (field) {
          var value = result[field];
          var fieldLabel = t("field_" + field) || field;
          list.appendChild(el("dt", null, fieldLabel));
          list.appendChild(el("dd", {
            text: value === null || value === undefined ? "—" : String(value),
          }));
        });
        return list;
      }).forEach(function (node) { block.appendChild(node); });
      subRow.appendChild(block);
    });
    children.push(subRow);
    details.appendChild(section("section-identity", t("section_identity"), children));
  }

  function renderIntent(details, snapshot) {
    var intent = snapshot.intent;
    var children = [];

    var summaryBlock = el("div", null, el("h3", null, t("heading_summary")));
    assertionNodes(intent.summary, function (result) {
      return el("p", { class: "fact-value", text: String(result) });
    }).forEach(function (node) { summaryBlock.appendChild(node); });

    var contractBlock = el("div", null, el("h3", null, t("heading_contract")));
    assertionNodes(intent.contract, function (result) {
      return kv(
        t("term_open_fields"), result.openFields.length ? result.openFields.join(", ") : t("val_none"),
        t("term_assumed_fields"), result.assumedFields.length ? result.assumedFields.join(", ") : t("val_none"),
        t("term_stale_fields"), result.staleFields.length ? result.staleFields.join(", ") : t("val_none"),
        t("term_blocking"), result.blocking ? t("val_blocking_yes") : t("val_blocking_no")
      );
    }).forEach(function (node) { contractBlock.appendChild(node); });

    var subRow = el("div", { class: "sub-cards-row" }, summaryBlock, contractBlock);
    children.push(subRow);

    var criteriaList = el("ul", { class: "plain-list" });
    if (!intent.criteria.length) {
      criteriaList.appendChild(emptyNote(t("empty_acceptance_criteria")));
    } else {
      intent.criteria.forEach(function (criterion) {
        var item = el("li", null);
        assertionNodes(criterion, function (result) {
          return kv(
            t("term_criterion"), result.criterionId,
            t("term_title"), result.title,
            t("term_given"), result.given,
            t("term_when"), result.when,
            t("term_then"), result.then
          );
        }).forEach(function (node) { item.appendChild(node); });
        criteriaList.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, t("heading_acceptance_criteria")), criteriaList));

    details.appendChild(section("section-intent", t("section_intent"), children));
  }

  function renderExecution(details, snapshot) {
    var execution = snapshot.execution;
    var children = [];

    var progressBlock = el("div", null, el("h3", null, t("heading_progress")));
    assertionNodes(execution.progress, function (result) {
      var list = el("ul", { class: "stage-list" });
      if (!result.observedStages.length) {
        list.appendChild(emptyNote(t("empty_stages")));
      } else {
        result.observedStages.forEach(function (stage) {
          var stateClass = stage.presence === "present" ? "stage-state-present" : "";
          var isLatest = result.latestObservedStage !== null &&
            stage.stageId === result.latestObservedStage;
          if (isLatest) stateClass += " stage-state-latest";
          var presenceLabel = t("presence_" + stage.presence) || String(stage.presence);
          var item = el("li", null,
            el("span", {
              class: "stage-id",
              text: String(stage.stageId) + " (" + String(stage.label) + ")",
            }),
            el("span", {
              class: "stage-state " + stateClass,
              text: presenceLabel + (isLatest ? t("stage_latest_badge") : ""),
            })
          );
          if (stage.presence === "skipped" && stage.skipReason) {
            item.appendChild(el("span", {
              class: "stage-skip-reason",
              text: t("stage_skipped_prefix") + String(stage.skipReason),
            }));
          }
          list.appendChild(item);
        });
      }
      return list;
    }).forEach(function (node) { progressBlock.appendChild(node); });
    children.push(progressBlock);

    var previewBlock = el("div", null, el("h3", null, t("heading_preview")));
    assertionNodes(execution.preview, function (result) {
      return kv(t("term_state"), result.state, t("term_round"), result.round === null ? "—" : String(result.round));
    }).forEach(function (node) { previewBlock.appendChild(node); });

    var repairBlock = el("div", null, el("h3", null, t("heading_repair")));
    assertionNodes(execution.repair, function (result) {
      return kv(
        t("term_rounds"), String(result.rounds),
        t("term_close_reason"), result.closeReason === null ? t("val_open") : String(result.closeReason),
        t("term_waiting_for_human"), result.waitingForHuman ? t("val_yes") : t("val_no"),
        t("term_routes"), result.routes.length ? result.routes.join(", ") : t("val_none")
      );
    }).forEach(function (node) { repairBlock.appendChild(node); });

    var subRow = el("div", { class: "sub-cards-row" }, previewBlock, repairBlock);
    children.push(subRow);

    details.appendChild(section("section-execution", t("section_execution"), children));
  }

  function outcomeNode(outcome) {
    var outcomeStr = String(outcome);
    var label = t("outcome_" + outcomeStr.toLowerCase()) || outcomeStr;
    return el("span", {
      class: "outcome outcome-" + outcomeStr.toLowerCase(),
      text: label,
    });
  }

  function renderEvaluation(details, snapshot) {
    var evaluation = snapshot.evaluation;
    var children = [];

    var verdictBlock = el("div", null, el("h3", null, t("heading_verdict")));
    assertionNodes(evaluation.verdict, function (result) {
      return el("p", { class: "fact-value" }, outcomeNode(result));
    }).forEach(function (node) { verdictBlock.appendChild(node); });

    var coverageBlock = el("div", null, el("h3", null, t("heading_coverage")));
    assertionNodes(evaluation.coverage, function (result) {
      return kv(
        t("term_declared"), String(result.declared),
        t("term_reviewed"), String(result.reviewed),
        t("term_unreviewed"), String(result.unreviewed),
        t("term_complete"), result.complete ? t("val_yes") : t("val_no")
      );
    }).forEach(function (node) { coverageBlock.appendChild(node); });

    var subRow = el("div", { class: "sub-cards-row" }, verdictBlock, coverageBlock);
    children.push(subRow);

    var criteriaList = el("ul", { class: "plain-list" });
    if (!evaluation.criteria.length) {
      criteriaList.appendChild(emptyNote(t("empty_criterion_evals")));
    } else {
      evaluation.criteria.forEach(function (criterion) {
        var item = el("li");
        assertionNodes(criterion, function (result) {
          var nodes = [];
          nodes.push(kv(
            t("term_criterion"), result.criterionId,
            t("term_outcome"), outcomeNode(result.outcome),
            t("term_required_proof"), result.requiredProof,
            t("term_observed_summary"), result.observedSummary
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
            nodes.push(el("div", null, el("h3", null, t("heading_evidence")), bindings));
          }
          var wrap = el("div");
          nodes.forEach(function (n) { wrap.appendChild(n); });
          return wrap;
        }).forEach(function (node) { item.appendChild(node); });
        criteriaList.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, t("heading_criterion_evals")), criteriaList));

    var findingsList = el("ul", { class: "plain-list" });
    if (!evaluation.findings.length) {
      findingsList.appendChild(emptyNote(t("empty_findings")));
    } else {
      evaluation.findings.forEach(function (finding) {
        var item = el("li");
        assertionNodes(finding, function (result) {
          return kv(
            t("term_finding"), result.findingId,
            t("term_issue"), result.issue,
            t("term_severity"), result.severity,
            t("term_disposition"), result.disposition,
            t("term_owner"), result.owner && result.owner.domainId ? String(result.owner.domainId)
              : (result.owner ? String(result.owner.kind) : t("unspecified")),
            t("term_repair"), result.repair
          );
        }).forEach(function (node) { item.appendChild(node); });
        findingsList.appendChild(item);
      });
    }
    children.push(el("div", null, el("h3", null, t("heading_findings")), findingsList));

    details.appendChild(section("section-evaluation", t("section_evaluation"), children));
  }

  /* ---------------------------------------------------------------- */
  /* Next actions, copy control, and unavailable role/export controls.  */
  /* ---------------------------------------------------------------- */

  function copyPlainText(text, statusNode) {
    function report(ok) {
      statusNode.textContent = ok
        ? t("copy_success")
        : t("copy_failed");
    }
    function fallback() {
      var area = el("textarea", { class: "sr-only", readonly: "readonly", tabindex: "-1" });
      area.value = text;
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      if (area.parentNode) area.parentNode.removeChild(area);
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
      reason = t("copy_unavail_state", { state: assertion ? String(assertion.availability) : t("assertion_absent") });
    } else if (typeof command !== "string" || command.length === 0) {
      reason = t("copy_unavail_no_cmd");
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
        }, t("copy_agent_command")),
        reasonNode);
    }
    var status = el("span", { class: "copy-status", role: "status", text: "" });
    var button = el("button", { type: "button", class: "button" },
      t("copy_agent_command_plain"));
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
    var roleKey = "limitation_role_attestation_owner_unmapped";
    var roleReason = (currentLang === "zh-CN" ? t(roleKey) : null) ||
      limitationSummary(items, "role-attestation-owner-unmapped") ||
      t("role_reason_default");
    var exportKey = "limitation_diagnostic_export_contract_unavailable";
    var exportReason = (currentLang === "zh-CN" ? t(exportKey) : null) ||
      limitationSummary(items, "diagnostic-export-contract-unavailable") ||
      t("export_reason_default");
    return el("div", { class: "sub-card" },
      el("h3", null, t("heading_unavail_controls")),
      el("div", { class: "action-card" },
        el("button", {
          type: "button", class: "button", disabled: "disabled",
          "aria-describedby": "unavailable-role-reason",
        }, t("attest_role")),
        el("span", { class: "unavailable-reason", id: "unavailable-role-reason", text: roleReason })),
      el("div", { class: "action-card" },
        el("button", {
          type: "button", class: "button", disabled: "disabled",
          "aria-describedby": "unavailable-export-reason",
        }, t("export_diagnostics")),
        el("span", { class: "unavailable-reason", id: "unavailable-export-reason", text: exportReason })));
  }

  function renderNextActions(details, snapshot) {
    var children = [];

    var primaryBlock = el("div", { class: "sub-card" }, el("h3", null, t("heading_primary_action")));
    assertionNodes(snapshot.nextActions.primary, function (result) {
      var owner = result.owner || {};
      var ownerActor = String(owner.actor || t("unspecified"));
      var ownerText = t("owner_prefix", { actor: ownerActor });
      if (owner.role) {
        ownerText += t("role_suffix", { role: String(owner.role) });
      }
      ownerText += t("kind_prefix", { kind: String(result.kind || t("unspecified")) });
      var card = el("div", { class: "action-card action-card-primary" },
        el("p", { class: "action-label", text: String(result.label) }),
        el("p", { class: "fact-meta", text: ownerText }));
      return card;
    }).forEach(function (node) { primaryBlock.appendChild(node); });
    primaryBlock.appendChild(copyControl(snapshot.nextActions.primary));
    children.push(primaryBlock);

    var alternatives = el("ul", { class: "plain-list" });
    if (!snapshot.nextActions.alternatives.length) {
      alternatives.appendChild(emptyNote(t("empty_alternatives")));
    } else {
      snapshot.nextActions.alternatives.forEach(function (alternative) {
        var item = el("li");
        assertionNodes(alternative, function (result) {
          var owner = result.owner || {};
          var ownerActor = String(owner.actor || t("unspecified"));
          var ownerText = t("owner_prefix", { actor: ownerActor });
          if (owner.role) {
            ownerText += t("role_suffix", { role: String(owner.role) });
          }
          ownerText += t("kind_prefix", { kind: String(result.kind || t("unspecified")) });
          return el("div", { class: "action-card" },
            el("p", { class: "action-label", text: String(result.label) }),
            el("p", { class: "fact-meta", text: ownerText }));
        }).forEach(function (node) { item.appendChild(node); });
        alternatives.appendChild(item);
      });
    }
    children.push(el("div", { class: "sub-card" }, el("h3", null, t("heading_alternatives")), alternatives));
    children.push(unavailableControls(snapshot.limitations.items || []));

    details.appendChild(section("section-next-actions", t("section_next_actions"), children));
  }

  function renderLimitations(details, snapshot) {
    var list = el("ul", { class: "plain-list" });
    if (!snapshot.limitations.items.length) {
      list.appendChild(emptyNote(t("empty_limitations")));
    } else {
      snapshot.limitations.items.forEach(function (item) {
        var node = el("li");
        assertionNodes(item, function (result) {
          var code = String(result.code);
          var codeKey = "limitation_" + code.replace(/-/g, "_");
          var summary = (currentLang === "zh-CN" ? t(codeKey) : null) || String(result.summary);
          return el("div", null,
            el("p", null,
              el("span", { class: "reason-code", text: code }),
              " — " + summary),
            result.affectsAssertionIds.length
              ? el("p", { class: "fact-meta",
                  text: t("affects_prefix") + result.affectsAssertionIds.join(", ") })
              : null);
        }).forEach(function (child) { node.appendChild(child); });
        list.appendChild(node);
      });
    }
    details.appendChild(section("section-limitations", t("section_limitations"), [list]));
  }

  /* ---------------------------------------------------------------- */
  /* Sources with on-demand text excerpts.                              */
  /* ---------------------------------------------------------------- */

  function excerptErrorMessage(code) {
    if (code === "SOURCE_HASH_MISMATCH") {
      return t("excerpt_err_hash_mismatch");
    }
    if (code === "SESSION_TOKEN_INVALID") {
      return t("excerpt_err_closed");
    }
    if (code === "SOURCE_LOCATOR_INVALID") {
      return t("excerpt_err_locator");
    }
    return t("excerpt_err_generic", { code: String(code) });
  }

  function fetchExcerpt(record, area) {
    area.textContent = "";
    area.appendChild(el("p", {
      class: "excerpt-state",
      text: t("excerpt_loading"),
    }));
    var path = "/api/v1/sources/" + encodeURIComponent(record.locator) +
      "?expectedHash=" + encodeURIComponent(record.verifiedHash);
    requestJson(path).then(function (result) {
      area.textContent = "";
      if (result.status === 200 && result.body && result.body.excerpt !== undefined) {
        var truncText = result.body.truncated ? t("truncated_text") : "";
        area.appendChild(el("p", { class: "excerpt-state" },
          t("excerpt_served_for", {
            sourceRef: String(result.body.sourceRef || record.sourceRef),
            truncated: truncText,
          })));
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
        text: t("excerpt_err_unreachable"),
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
          ? t("source_unavail_no_locator")
          : t("source_unavail_read_state", { readState: String(record.readState) });
        list.appendChild(el("li", null,
          el("span", { class: "reason-code", text: String(record.sourceRef) }),
          el("p", { class: "unavailable-reason", text: reason })));
        return;
      }
      var area = el("div");
      var kindKey = "kind_" + String(record.kind).replace(/-/g, "_");
      var kindLabel = t(kindKey) || String(record.kind);
      var readStateLabel = t("readState_" + record.readState) || String(record.readState);
      var summaryText = t("source_summary_line", {
        sourceRef: String(record.sourceRef),
        kind: kindLabel,
        readState: readStateLabel,
      });
      if (record.freshness !== "current") {
        summaryText += t("freshness_suffix", { freshness: String(record.freshness) });
      }
      var detailsNode = el("details", { class: "source" },
        el("summary", null, summaryText),
        el("div", { class: "source-body" },
          kv(
            t("term_authority"), String(record.authorityKey),
            t("term_observed_hash"), record.observedHash === null ? null : String(record.observedHash),
            t("term_verified_hash"), record.verifiedHash === null ? null : String(record.verifiedHash),
            t("term_verified_at"), record.verifiedAt === null ? null : String(record.verifiedAt)
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
    details.appendChild(section("section-sources", t("section_sources"), [
      el("p", { class: "section-hint", text: t("sources_hint") }),
      list,
    ]));
  }

  /* ---------------------------------------------------------------- */
  /* Snapshot rendering entry point.                                    */
  /* ---------------------------------------------------------------- */

  function renderSnapshot(snapshot) {
    renderBuildState(snapshot);

    var runId = snapshot.identity.run && snapshot.identity.run.result
      ? snapshot.identity.run.result.runId : t("unknown_run");
    document.getElementById("run-id-line").textContent =
      t("run_line", {
        runId: String(runId),
        builtAt: String(snapshot.identity.snapshot.builtAt || ""),
      });

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
      var mainEl = document.getElementById("main");
      if (mainEl) mainEl.focus();
    }
  }

  /* ---------------------------------------------------------------- */
  /* Bootstrap.                                                         */
  /* ---------------------------------------------------------------- */

  function init() {
    var reloadBtn = document.getElementById("reload-button");
    if (reloadBtn) reloadBtn.addEventListener("click", loadSnapshot);

    var refreshBtn = document.getElementById("refresh-button");
    if (refreshBtn) refreshBtn.addEventListener("click", refreshSnapshot);

    var langBtn = document.getElementById("lang-toggle-button");
    if (langBtn) {
      langBtn.addEventListener("click", toggleLanguage);
    }

    Array.prototype.forEach.call(
      document.querySelectorAll("[data-reload]"),
      function (button) { button.addEventListener("click", loadSnapshot); }
    );

    window.addEventListener("keydown", function (e) {
      var key = e.key;
      var isLang = key === "l" || key === "L";
      var isRefresh = key === "r" || key === "R";
      if (!isLang && !isRefresh) return;
      var active = document.activeElement;
      var tag = active ? active.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select" || (active && active.isContentEditable)) {
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isRefresh) {
        /* The refresh control exists only while a snapshot is rendered. */
        var readyView = document.getElementById("view-ready");
        if (!readyView || readyView.hidden) return;
        e.preventDefault();
        refreshSnapshot();
        return;
      }
      e.preventDefault();
      toggleLanguage();
    });

    factGridKeyboard();
    updateStaticTexts();

    sessionToken = readTokenFromFragment();
    if (!sessionToken) {
      showView("no-token", true);
      return;
    }
    loadSnapshot();
  }

  init();
})();

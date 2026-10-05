// Workbench project entry. Vanilla ES module: no framework, no storage,
// no remote request. The session token lives in this module's memory only.

const state = {
  token: null,
  panelTriggerStack: [],
  currentProjectId: null,
  projects: [],
  candidate: null,
  proposalsProject: null,
  proposals: [],
  details: new Map(),
  assetsProject: null,
  assets: [],
  selectedAssetId: null,
  selectedAsset: null,
  tokensProject: null,
  tokensAsset: null,
  tokensThemes: [],
  documentProject: null,
  documentAsset: null,
  canvasProject: null,
  canvases: [],
  canvas: null,
  canvasDocument: null,
  canvasCounter: 0,
  canvasBoardId: null,
  canvasSelection: [],
  canvasHistory: { canUndo: false, canRedo: false },
  canvasInstances: new Map(),
  canvasQueue: [],
  canvasSaveState: "idle",
  canvasView: { scale: 1, x: 0, y: 0 },
  canvasTimers: { debounce: null, deadline: null },
  canvasSnapshotUrl: null,
  snapshots: [],
  context: null,
  workProject: null,
  workRequests: [],
  workSelectedId: null,
  ownerProject: null,
  ownerRuns: [],
  ownerRun: null,
  lifeProject: null,
  lifeData: null,
  lifeSelected: null,
  lifeRefReport: null,
};

const elements = {
  sessionState: document.getElementById("session-state"),
  sessionError: document.getElementById("session-error"),
  sessionErrorMessage: document.getElementById("session-error-message"),
  probeForm: document.getElementById("probe-form"),
  probeButton: document.getElementById("probe-button"),
  projectPath: document.getElementById("project-path"),
  candidate: document.getElementById("candidate"),
  candidatePath: document.getElementById("candidate-path"),
  candidateIdentity: document.getElementById("candidate-identity"),
  candidateScope: document.getElementById("candidate-scope"),
  registerForm: document.getElementById("register-form"),
  registerButton: document.getElementById("register-button"),
  projectName: document.getElementById("project-name"),
  cancelCandidate: document.getElementById("cancel-candidate"),
  refreshButton: document.getElementById("refresh-button"),
  listEmpty: document.getElementById("list-empty"),
  listError: document.getElementById("list-error"),
  table: document.getElementById("project-table"),
  rows: document.getElementById("project-rows"),
  rowTemplate: document.getElementById("project-row-template"),
  live: document.getElementById("live"),
  proposalsPanel: document.getElementById("proposals-panel"),
  proposalsHeading: document.getElementById("proposals-heading"),
  proposalsScope: document.getElementById("proposals-scope"),
  proposalsError: document.getElementById("proposals-error"),
  proposalsEmpty: document.getElementById("proposals-empty"),
  proposalItems: document.getElementById("proposal-items"),
  proposalTemplate: document.getElementById("proposal-template"),
  proposalsClose: document.getElementById("proposals-close"),
  assetsPanel: document.getElementById("assets-panel"),
  assetsHeading: document.getElementById("assets-heading"),
  assetsScope: document.getElementById("assets-scope"),
  assetsFilter: document.getElementById("assets-filter"),
  assetsQuery: document.getElementById("assets-query"),
  assetsKind: document.getElementById("assets-kind"),
  assetsCapability: document.getElementById("assets-capability"),
  assetsError: document.getElementById("assets-error"),
  assetsEmpty: document.getElementById("assets-empty"),
  assetItems: document.getElementById("asset-items"),
  assetTemplate: document.getElementById("asset-template"),
  assetDetail: document.getElementById("asset-detail"),
  assetDetailHeading: document.getElementById("asset-detail-heading"),
  assetDetailKind: document.getElementById("asset-detail-kind"),
  assetDetailLifecycle: document.getElementById("asset-detail-lifecycle"),
  assetDetailCapabilities: document.getElementById("asset-detail-capabilities"),
  assetDetailRevision: document.getElementById("asset-detail-revision"),
  assetManifest: document.getElementById("asset-manifest"),
  assetLocators: document.getElementById("asset-locators"),
  assetWarnings: document.getElementById("asset-warnings"),
  assetPreviewFrame: document.getElementById("asset-preview-frame"),
  assetPreviewNote: document.getElementById("asset-preview-note"),
  assetPreviewStatic: document.getElementById("asset-preview-static"),
  assetPreviewDynamic: document.getElementById("asset-preview-dynamic"),
  assetPreviewEnable: document.getElementById("asset-preview-enable"),
  assetDesignSystemControls: document.getElementById("asset-design-system-controls"),
  assetDesignSystem: document.getElementById("asset-design-system"),
  assetDesignSystemHint: document.getElementById("asset-design-system-hint"),
  assetsClose: document.getElementById("assets-close"),
  tokensPanel: document.getElementById("tokens-panel"),
  tokensHeading: document.getElementById("tokens-heading"),
  tokensScope: document.getElementById("tokens-scope"),
  tokensError: document.getElementById("tokens-error"),
  tokensValidation: document.getElementById("tokens-validation"),
  tokensValidationErrors: document.getElementById("tokens-validation-errors"),
  tokensDocument: document.getElementById("tokens-document"),
  tokensSave: document.getElementById("tokens-save"),
  tokensPublish: document.getElementById("tokens-publish"),
  tokensReload: document.getElementById("tokens-reload"),
  tokensStatus: document.getElementById("tokens-status"),
  tokensTheme: document.getElementById("tokens-theme"),
  tokensPreviewRefresh: document.getElementById("tokens-preview-refresh"),
  tokensPreviewNote: document.getElementById("tokens-preview-note"),
  tokensPreviewFrame: document.getElementById("tokens-preview-frame"),
  tokensDiffButton: document.getElementById("tokens-diff-button"),
  tokensDiffCounts: document.getElementById("tokens-diff-counts"),
  tokensDiff: document.getElementById("tokens-diff"),
  tokensAffectedNote: document.getElementById("tokens-affected-note"),
  tokensAffected: document.getElementById("tokens-affected"),
  tokensBaselineForm: document.getElementById("tokens-baseline-form"),
  tokensBaselinePath: document.getElementById("tokens-baseline-path"),
  tokensBaselineButton: document.getElementById("tokens-baseline-button"),
  tokensBaselineResult: document.getElementById("tokens-baseline-result"),
  tokensClose: document.getElementById("tokens-close"),
  assetDocumentControls: document.getElementById("asset-document-controls"),
  assetDocumentHint: document.getElementById("asset-document-hint"),
  assetOpenDocument: document.getElementById("asset-open-document"),
  createComponent: document.getElementById("create-component"),
  createPage: document.getElementById("create-page"),
  documentPanel: document.getElementById("document-panel"),
  documentHeading: document.getElementById("document-heading"),
  documentScope: document.getElementById("document-scope"),
  documentError: document.getElementById("document-error"),
  documentValidation: document.getElementById("document-validation"),
  documentValidationErrors: document.getElementById("document-validation-errors"),
  documentEditorTitle: document.getElementById("document-editor-title"),
  documentEditorHint: document.getElementById("document-editor-hint"),
  documentText: document.getElementById("document-text"),
  documentSave: document.getElementById("document-save"),
  documentPublish: document.getElementById("document-publish"),
  documentReload: document.getElementById("document-reload"),
  documentStatus: document.getElementById("document-status"),
  componentInstance: document.getElementById("component-instance"),
  instanceParams: document.getElementById("instance-params"),
  instanceRender: document.getElementById("instance-render"),
  instanceNote: document.getElementById("instance-note"),
  instanceVariants: document.getElementById("instance-variants"),
  instanceStates: document.getElementById("instance-states"),
  instanceSlots: document.getElementById("instance-slots"),
  instanceFrame: document.getElementById("instance-frame"),
  pageDistill: document.getElementById("page-distill"),
  distillForm: document.getElementById("distill-form"),
  distillNodes: document.getElementById("distill-nodes"),
  distillName: document.getElementById("distill-name"),
  distillResult: document.getElementById("distill-result"),
  documentClose: document.getElementById("document-close"),
  canvasPanel: document.getElementById("canvas-panel"),
  canvasHeading: document.getElementById("canvas-heading"),
  canvasScope: document.getElementById("canvas-scope"),
  canvasError: document.getElementById("canvas-error"),
  canvasCreateForm: document.getElementById("canvas-create-form"),
  canvasName: document.getElementById("canvas-name"),
  canvasSelect: document.getElementById("canvas-select"),
  canvasReload: document.getElementById("canvas-reload"),
  canvasFork: document.getElementById("canvas-fork"),
  canvasRetry: document.getElementById("canvas-retry"),
  canvasSaveState: document.getElementById("canvas-save-state"),
  canvasBoardSelect: document.getElementById("canvas-board"),
  canvasBoardAdd: document.getElementById("canvas-board-add"),
  canvasZoomIn: document.getElementById("canvas-zoom-in"),
  canvasZoomOut: document.getElementById("canvas-zoom-out"),
  canvasZoomLabel: document.getElementById("canvas-zoom-label"),
  canvasFit: document.getElementById("canvas-fit"),
  canvasUndo: document.getElementById("canvas-undo"),
  canvasRedo: document.getElementById("canvas-redo"),
  canvasGroup: document.getElementById("canvas-group"),
  canvasDuplicate: document.getElementById("canvas-duplicate"),
  canvasDelete: document.getElementById("canvas-delete"),
  canvasSnapshot: document.getElementById("canvas-snapshot"),
  canvasSnapshotNote: document.getElementById("canvas-snapshot-note"),
  canvasSnapshotFrame: document.getElementById("canvas-snapshot-frame"),
  canvasViewport: document.getElementById("canvas-viewport"),
  canvasStage: document.getElementById("canvas-stage"),
  canvasSelection: document.getElementById("canvas-selection"),
  canvasNodeProps: document.getElementById("canvas-node-props"),
  canvasBoardProps: document.getElementById("canvas-board-props"),
  canvasInstanceProps: document.getElementById("canvas-instance-props"),
  canvasInstanceInfo: document.getElementById("canvas-instance-info"),
  canvasInstanceParams: document.getElementById("canvas-instance-params"),
  canvasInstanceApply: document.getElementById("canvas-instance-apply"),
  canvasInstanceUpgrade: document.getElementById("canvas-instance-upgrade"),
  canvasDirtyNote: document.getElementById("canvas-dirty-note"),
  propX: document.getElementById("prop-x"),
  propY: document.getElementById("prop-y"),
  propWidth: document.getElementById("prop-width"),
  propHeight: document.getElementById("prop-height"),
  propContent: document.getElementById("prop-content"),
  propContentLabel: document.getElementById("prop-content-label"),
  propContentApply: document.getElementById("prop-content-apply"),
  propToken: document.getElementById("prop-token"),
  propTokenApply: document.getElementById("prop-token-apply"),
  boardWidth: document.getElementById("board-width"),
  boardHeight: document.getElementById("board-height"),
  boardResize: document.getElementById("board-resize"),
  canvasClose: document.getElementById("canvas-close"),
  assetCanvasControls: document.getElementById("asset-canvas-controls"),
  assetIntoCanvas: document.getElementById("asset-into-canvas"),
  assetItemsList: document.getElementById("asset-items"),
  flowFrom: document.getElementById("flow-from"),
  flowTo: document.getElementById("flow-to"),
  flowKind: document.getElementById("flow-kind"),
  flowLabel: document.getElementById("flow-label"),
  flowAdd: document.getElementById("flow-add"),
  flowList: document.getElementById("flow-list"),
  flowError: document.getElementById("flow-error"),
  schemeWidth: document.getElementById("scheme-width"),
  schemeHeight: document.getElementById("scheme-height"),
  schemeDevice: document.getElementById("scheme-device"),
  schemeRules: document.getElementById("scheme-rules"),
  schemeRegions: document.getElementById("scheme-regions"),
  schemeAcceptance: document.getElementById("scheme-acceptance"),
  schemeSave: document.getElementById("scheme-save"),
  schemeDerive: document.getElementById("scheme-derive"),
  schemeNote: document.getElementById("scheme-note"),
  schemeError: document.getElementById("scheme-error"),
  snapshotCreate: document.getElementById("snapshot-create"),
  snapshotList: document.getElementById("snapshot-list"),
  compareLeft: document.getElementById("compare-left"),
  compareRight: document.getElementById("compare-right"),
  compareRun: document.getElementById("compare-run"),
  compareNote: document.getElementById("compare-note"),
  compareGrid: document.getElementById("compare-grid"),
  compareLeftFrame: document.getElementById("compare-left-frame"),
  compareRightFrame: document.getElementById("compare-right-frame"),
  compareLeftCaption: document.getElementById("compare-left-caption"),
  compareRightCaption: document.getElementById("compare-right-caption"),
  contextBuild: document.getElementById("context-build"),
  contextConfirm: document.getElementById("context-confirm"),
  contextFiles: document.getElementById("context-files"),
  contextState: document.getElementById("context-state"),
  contextStale: document.getElementById("context-stale"),
  contextContent: document.getElementById("context-content"),
  contextExclusions: document.getElementById("context-exclusions"),
  contextError: document.getElementById("context-error"),
  workPanel: document.getElementById("work-panel"),
  workHeading: document.getElementById("work-heading"),
  workScope: document.getElementById("work-scope"),
  workError: document.getElementById("work-error"),
  workList: document.getElementById("work-list"),
  workDetail: document.getElementById("work-detail"),
  workDetailHeading: document.getElementById("work-detail-heading"),
  workDetailState: document.getElementById("work-detail-state"),
  workDetailCapability: document.getElementById("work-detail-capability"),
  workDetailContext: document.getElementById("work-detail-context"),
  workDetailExpiry: document.getElementById("work-detail-expiry"),
  workDetailPlan: document.getElementById("work-detail-plan"),
  workHandoff: document.getElementById("work-handoff"),
  workHandoffNote: document.getElementById("work-handoff-note"),
  workAttempt: document.getElementById("work-attempt"),
  workAttempts: document.getElementById("work-attempts"),
  workResult: document.getElementById("work-result"),
  workResultList: document.getElementById("work-result-list"),
  workTitle: document.getElementById("work-title"),
  workGoal: document.getElementById("work-goal"),
  workStack: document.getElementById("work-stack"),
  workExpiry: document.getElementById("work-expiry"),
  workReuse: document.getElementById("work-reuse"),
  workAdapt: document.getElementById("work-adapt"),
  workNew: document.getElementById("work-new"),
  workRequired: document.getElementById("work-required"),
  workContextNote: document.getElementById("work-context-note"),
  workCreate: document.getElementById("work-create"),
  workReload: document.getElementById("work-reload"),
  workConsent: document.getElementById("work-consent"),
  workCancel: document.getElementById("work-cancel"),
  workConfirmCancel: document.getElementById("work-confirm-cancel"),
  workRetry: document.getElementById("work-retry"),
  workReject: document.getElementById("work-reject"),
  workCopyHandoff: document.getElementById("work-copy-handoff"),
  workClose: document.getElementById("work-close"),
  ownerPanel: document.getElementById("owner-panel"),
  ownerHeading: document.getElementById("owner-heading"),
  ownerScope: document.getElementById("owner-scope"),
  ownerError: document.getElementById("owner-error"),
  ownerRun: document.getElementById("owner-run"),
  ownerReload: document.getElementById("owner-reload"),
  ownerRunNote: document.getElementById("owner-run-note"),
  ownerCriteria: document.getElementById("owner-criteria"),
  ownerEvidence: document.getElementById("owner-evidence"),
  ownerFindings: document.getElementById("owner-findings"),
  ownerConfirmations: document.getElementById("owner-confirmations"),
  ownerClose: document.getElementById("owner-close"),
  lifePanel: document.getElementById("life-panel"),
  lifeHeading: document.getElementById("life-heading"),
  lifeScope: document.getElementById("life-scope"),
  lifeError: document.getElementById("life-error"),
  lifeFilter: document.getElementById("life-filter"),
  lifeReload: document.getElementById("life-reload"),
  lifeProjectArchive: document.getElementById("life-project-archive"),
  lifeProjectUnarchive: document.getElementById("life-project-unarchive"),
  lifeProjectNote: document.getElementById("life-project-note"),
  lifeList: document.getElementById("life-list"),
  lifeDetail: document.getElementById("life-detail"),
  lifeDetailName: document.getElementById("life-detail-name"),
  lifeDetailState: document.getElementById("life-detail-state"),
  lifeArchive: document.getElementById("life-archive"),
  lifeUnarchive: document.getElementById("life-unarchive"),
  lifeTrash: document.getElementById("life-trash"),
  lifeRestore: document.getElementById("life-restore"),
  lifeReferences: document.getElementById("life-references"),
  lifeDelete: document.getElementById("life-delete"),
  lifeDeleteConfirm: document.getElementById("life-delete-confirm"),
  lifeDeleteConfirmBody: document.getElementById("life-delete-confirm-body"),
  lifeDeleteCancel: document.getElementById("life-delete-cancel"),
  lifeDeleteConfirmButton:
    document.getElementById("life-delete-confirm-button"),
  lifeRefsNote: document.getElementById("life-refs-note"),
  lifeRefs: document.getElementById("life-refs"),
  lifeClose: document.getElementById("life-close"),
  settingsOpen: document.getElementById("settings-open"),
  settingsPanel: document.getElementById("settings-panel"),
  settingsError: document.getElementById("settings-error"),
  settingsDiagnostics: document.getElementById("settings-diagnostics"),
  settingsClose: document.getElementById("settings-close"),
  backupDest: document.getElementById("backup-dest"),
  backupCreate: document.getElementById("backup-create"),
  backupNote: document.getElementById("backup-note"),
  backupVerifyPath: document.getElementById("backup-verify-path"),
  backupVerify: document.getElementById("backup-verify"),
  backupVerifyNote: document.getElementById("backup-verify-note"),
  restorePath: document.getElementById("restore-path"),
  restoreTarget: document.getElementById("restore-target"),
  restoreRun: document.getElementById("restore-run"),
  restoreNote: document.getElementById("restore-note"),
};

function announce(message) {
  elements.live.textContent = "";
  window.setTimeout(() => {
    elements.live.textContent = message;
  }, 10);
}

function newOperationId() {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return "op_" + hex;
}

function workspacePanels() {
  return [elements.assetsPanel, elements.tokensPanel, elements.documentPanel,
    elements.proposalsPanel, elements.canvasPanel, elements.workPanel,
    elements.ownerPanel, elements.lifePanel, elements.settingsPanel];
}

function focusIntoPanel(target) {
  const trigger = document.activeElement;
  const panel = target.closest(".panel");
  const panels = workspacePanels();
  // A sibling opened from the project list starts a new navigation path.
  // Nested editors retain their parent and restore it when they close.
  if (!panels.some((item) => item !== panel && item.contains(trigger))) {
    state.panelTriggerStack = [];
  }
  state.panelTriggerStack.push(trigger instanceof HTMLElement ? trigger : null);
  for (const sibling of panels) sibling.hidden = sibling !== panel;
  target.setAttribute("tabindex", "-1");
  target.focus();
}

function restorePanelTrigger() {
  const trigger = state.panelTriggerStack.pop();
  if (!trigger || !document.contains(trigger)) return;
  const parent = trigger.closest(".panel");
  if (workspacePanels().includes(parent)) parent.hidden = false;
  if (!trigger.closest("[hidden]")) trigger.focus();
}

function formatLocalTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function setSessionState(text, kind, audit) {
  elements.sessionState.textContent = text;
  elements.sessionState.dataset.state = kind;
  // The exact server stamp stays available for audit, never as the label.
  if (audit) elements.sessionState.title = audit;
  else elements.sessionState.removeAttribute("title");
}

function failSession(message) {
  setSessionState("会话不可用", "failed");
  elements.sessionError.hidden = false;
  elements.sessionErrorMessage.textContent = message;
  elements.probeForm.hidden = true;
}

async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = "Bearer " + state.token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    referrerPolicy: "no-referrer",
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }
  if (!response.ok) {
    const failure = new Error(
      payload && payload.error ? payload.error.message : "请求被拒绝"
    );
    failure.code = payload && payload.error ? payload.error.code : "unknown";
    failure.status = response.status;
    failure.retryable = Boolean(payload && payload.error && payload.error.retryable);
    throw failure;
  }
  return payload;
}

function mutation(operationId, payload, expectedCounter) {
  const envelope = { operationId, payload };
  if (typeof expectedCounter === "number") envelope.expectedCounter = expectedCounter;
  return envelope;
}

function describeFailure(error, action) {
  const code = error.code || "unknown";
  // The code stays in the sentence (existing contract, asserted by the
  // browser suite) so a report can be traced; the action is added.
  console.debug("workbench-failure", action, code, error.message);
  if (code === "conflict") {
    return (
      `${action}失败：项目状态已变化（conflict）。` +
      "列表已刷新，请基于新状态重试。"
    );
  }
  if (code === "disconnected") {
    return (
      `${action}失败：项目目录当前不可达（disconnected）。` +
      "请重新绑定该目录后重试。"
    );
  }
  if (code === "invalid-target") {
    return (
      `${action}失败：该目录不能作为项目目标（invalid-target）。` +
      "请填写已存在的绝对目录，" +
      "不要选择当前用户主目录本身、文件系统根目录、文件，或与工作台数据目录重叠的位置。"
    );
  }
  if (code === "unauthorized") {
    return (
      `${action}失败：当前凭证无权执行（unauthorized）。` +
      "请用启动服务时打印的链接重新打开本页面后再试。"
    );
  }
  if (code === "recovery-required") {
    return (
      `${action}失败：该项目有待恢复写入（recovery-required）。` +
      "请先完成或回滚该次恢复。"
    );
  }
  // An unmapped code keeps its raw message and code (traced by support),
  // and gains the next action the raw message never carries.
  return (
    `${action}失败：${error.message}（${code}）。请重试；` +
    "若持续出现，请在「设置与备份」的诊断区确认服务状态。"
  );
}

function grantLabel(scopes) {
  const labels = {
    read: "只读",
    write: "写入",
    execute: "执行",
    "model-send": "发送给模型",
  };
  if (!scopes || scopes.length === 0) return "无";
  return scopes.map((scope) => labels[scope] || scope).join("、");
}

function renderProjects() {
  elements.rows.textContent = "";
  const projects = state.projects;
  elements.listEmpty.hidden = projects.length > 0;
  elements.table.hidden = projects.length === 0;
  for (const project of projects) {
    const fragment = elements.rowTemplate.content.cloneNode(true);
    const row = fragment.querySelector("tr");
    row.dataset.projectId = project.projectId;
    const headers = elements.table.querySelectorAll("th");
    row.querySelectorAll("td").forEach((cell, index) => {
      cell.dataset.label = headers[index].textContent;
    });
    row.querySelector(".project-name").textContent = project.name;
    row.querySelector(".current-flag").hidden =
      project.projectId !== state.currentProjectId;
    row.querySelector(".project-path").textContent = project.canonicalPath;
    const badge = row.querySelector(".state-badge");
    const connected = project.connectionState === "connected";
    badge.dataset.state = project.connectionState;
    badge.textContent = connected
      ? "已连接"
      : project.connectionState === "disconnected"
        ? "已断开"
        : project.connectionState;
    row.querySelector(".grant-list").textContent = grantLabel(project.grantScopes);
    row.querySelector(".open-button").addEventListener("click", () => openProject(project));
    row.querySelector(".rename-button").addEventListener("click", () => renameProject(project));
    row.querySelector(".grants-button").addEventListener("click", () => editGrants(project));
    row.querySelector(".proposals-button").addEventListener("click", () => openProposals(project));
    row.querySelector(".canvas-button").addEventListener("click", () => openCanvas(project));
    row.querySelector(".work-button").addEventListener("click", () => openWork(project));
    row.querySelector(".owner-button").addEventListener("click", () => openOwner(project));
    row.querySelector(".life-button").addEventListener("click", () => openLifecycle(project));
    row.querySelector(".assets-button").addEventListener("click", () => openAssets(project));
    const rebind = row.querySelector(".rebind-button");
    rebind.hidden = connected;
    rebind.addEventListener("click", () => rebindProject(project));
    row.querySelector(".remove-button").addEventListener("click", () => removeProject(project));
    elements.rows.appendChild(fragment);
  }
}

async function loadProjects() {
  try {
    const payload = await api("/api/v1/projects");
    state.projects = payload.projects || [];
    state.currentProjectId = payload.currentProjectId || null;
    elements.listError.hidden = true;
    renderProjects();
  } catch (error) {
    if (error.status === 401) {
      failSession("会话已失效。请用启动时打印的 bootstrap 链接重新打开本页面。");
      return;
    }
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "读取项目列表");
  }
}

function resetCandidate() {
  state.candidate = null;
  elements.candidate.hidden = true;
  elements.projectName.value = "";
}

async function probeFolder(path, excludeProjectId) {
  const body = { path };
  if (excludeProjectId) body.excludeProjectId = excludeProjectId;
  return api("/api/v1/projects/probe", { method: "POST", body });
}

async function onProbe(event) {
  event.preventDefault();
  elements.probeButton.disabled = true;
  try {
    const payload = await probeFolder(elements.projectPath.value);
    state.candidate = payload.candidate;
    elements.candidatePath.textContent = payload.candidate.canonicalPath;
    elements.candidateIdentity.textContent = payload.candidate.directoryIdentity;
    elements.candidateScope.textContent = grantLabel(["read"]) + "（默认）";
    elements.projectName.placeholder = payload.candidate.suggestedName;
    elements.candidate.hidden = false;
    elements.registerButton.focus();
    announce("目录已检查，请核对规范化路径与目录身份后确认登记。");
  } catch (error) {
    resetCandidate();
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "检查目录");
    announce(elements.listError.textContent);
  } finally {
    elements.probeButton.disabled = false;
  }
}

async function onRegister(event) {
  event.preventDefault();
  if (!state.candidate) return;
  elements.registerButton.disabled = true;
  try {
    await api("/api/v1/projects", {
      method: "POST",
      body: {
        path: state.candidate.canonicalPath,
        candidateId: state.candidate.candidateId,
        name: elements.projectName.value,
        operation: mutation(newOperationId(), {
          action: "register-project",
          path: state.candidate.canonicalPath,
          candidateId: state.candidate.candidateId,
        }),
      },
    });
    resetCandidate();
    elements.projectPath.value = "";
    await loadProjects();
    announce("项目已登记为只读发现。写入、执行与模型发送需要单独授权。");
  } catch (error) {
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "登记项目");
    announce(elements.listError.textContent);
  } finally {
    elements.registerButton.disabled = false;
  }
}

async function openProject(project) {
  try {
    await api(`/api/v1/projects/${project.projectId}/actions/open`, {
      method: "POST",
      body: {
        operation: mutation(
          newOperationId(),
          { action: "open-project", projectId: project.projectId },
          0, // a setting write: the guard counter is always 0 (kind="setting")
        ),
      },
    });
    await loadProjects();
    announce(`当前项目已切换到 ${project.name}。`);
  } catch (error) {
    if (error.code === "conflict") await loadProjects();
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "切换项目");
  }
}

async function renameProject(project) {
  const name = window.prompt("新的项目名称", project.name);
  if (name === null) return;
  try {
    await api(`/api/v1/projects/${project.projectId}/actions/rename`, {
      method: "POST",
      body: {
        name,
        operation: mutation(
          newOperationId(),
          { action: "rename-project", projectId: project.projectId, name },
          project.counter
        ),
      },
    });
    await loadProjects();
    announce("项目已重命名。");
  } catch (error) {
    if (error.code === "conflict") await loadProjects();
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "重命名");
  }
}

async function editGrants(project) {
  const answer = window.prompt(
    "授权范围（逗号分隔，读取 read 始终保留）：\nread, write, execute, model-send",
    project.grantScopes.join(", ")
  );
  if (answer === null) return;
  const scopes = answer
    .split(",")
    .map((scope) => scope.trim())
    .filter(Boolean);
  try {
    await api(`/api/v1/projects/${project.projectId}/actions/grants`, {
      method: "POST",
      body: {
        scopes,
        operation: mutation(
          newOperationId(),
          { action: "set-grants", projectId: project.projectId, scopes },
          project.counter
        ),
      },
    });
    await loadProjects();
    announce("授权范围已更新。");
  } catch (error) {
    if (error.code === "conflict") await loadProjects();
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "更新授权");
  }
}

async function rebindProject(project) {
  const path = window.prompt(
    "该项目当前不可达。请输入重新绑定的绝对目录（不会自动匹配同名目录）：",
    project.canonicalPath
  );
  if (path === null || path.trim() === "") return;
  try {
    const probed = await probeFolder(path.trim(), project.projectId);
    const confirmed = window.confirm(
      `将 ${project.name} 重新绑定到：\n${probed.candidate.canonicalPath}\n` +
        `目录身份：${probed.candidate.directoryIdentity}\n\n确认继续？`
    );
    if (!confirmed) {
      announce("已取消重新绑定。");
      return;
    }
    await api(`/api/v1/projects/${project.projectId}/actions/rebind`, {
      method: "POST",
      body: {
        path: probed.candidate.canonicalPath,
        candidateId: probed.candidate.candidateId,
        operation: mutation(
          newOperationId(),
          {
            action: "rebind-project",
            projectId: project.projectId,
            canonicalPath: probed.candidate.canonicalPath,
            candidateId: probed.candidate.candidateId,
          },
          project.counter
        ),
      },
    });
    await loadProjects();
    announce("项目已重新绑定。");
  } catch (error) {
    if (error.code === "conflict") await loadProjects();
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "重新绑定");
  }
}

async function removeProject(project) {
  const confirmed = window.confirm(
    `移除项目登记「${project.name}」？\n\n` +
      "只解除工作台登记与目录授权，不会删除本地源文件。"
  );
  if (!confirmed) return;
  try {
    await api(`/api/v1/projects/${project.projectId}/actions/remove`, {
      method: "POST",
      body: {
        operation: mutation(
          newOperationId(),
          { action: "remove-project", projectId: project.projectId },
          project.counter
        ),
      },
    });
    await loadProjects();
    announce("项目登记已移除，本地文件未改动。");
  } catch (error) {
    if (error.code === "conflict") await loadProjects();
    elements.listError.hidden = false;
    elements.listError.textContent = describeFailure(error, "移除项目");
  }
}

// -- change proposals (WB-09) -------------------------------------------

const PROPOSAL_STATE_LABELS = {
  "awaiting-authorization": "等待授权",
  applied: "已应用",
  rejected: "已拒绝",
  expired: "已过期",
  "recovery-required": "需要恢复",
  "rolled-back": "已回滚",
};

function proposalStateLabel(value) {
  return PROPOSAL_STATE_LABELS[value] || value;
}

async function openProposals(project) {
  state.proposalsProject = project;
  elements.proposalsHeading.textContent = `变更提案 · ${project.name}`;
  elements.proposalsScope.textContent =
    `目录：${project.canonicalPath}（授权：${grantLabel(project.grantScopes)}）`;
  elements.proposalsPanel.hidden = false;
  elements.proposalsEmpty.hidden = true;
  elements.proposalsError.hidden = true;
  await loadProposals();
  focusIntoPanel(elements.proposalsHeading);
}

async function loadProposals() {
  const project = state.proposalsProject;
  if (!project) return;
  try {
    const listing = await api(`/api/v1/projects/${project.projectId}/proposals`);
    state.proposals = listing.proposals || [];
    state.details = new Map();
    for (const item of state.proposals) {
      const detail = await api(
        `/api/v1/projects/${project.projectId}/proposals/${item.proposalId}`
      );
      state.details.set(item.proposalId, detail.proposal);
    }
    elements.proposalsError.hidden = true;
    renderProposals();
  } catch (error) {
    elements.proposalsError.hidden = false;
    elements.proposalsError.textContent = describeFailure(error, "读取提案");
  }
}

function renderProposals() {
  elements.proposalItems.textContent = "";
  elements.proposalsEmpty.hidden = state.proposals.length > 0;
  for (const item of state.proposals) {
    const detail = state.details.get(item.proposalId) || item;
    const fragment = elements.proposalTemplate.content.cloneNode(true);
    const node = fragment.querySelector(".proposal-item");
    node.dataset.proposalId = item.proposalId;
    node.dataset.state = detail.state;
    node.querySelector(".proposal-summary").textContent =
      detail.summary || `${detail.changes.length} 个文件变更`;
    const badge = node.querySelector(".proposal-state");
    badge.dataset.state = detail.state;
    badge.textContent = proposalStateLabel(detail.state);
    const deps = Array.isArray(detail.dependencyChanges)
      ? detail.dependencyChanges
      : [];
    const depMeta = deps.length
      ? ` · 依赖变化 ${deps
          .map((dep) => (dep && dep.name ? dep.name : JSON.stringify(dep)))
          .join("、")}`
      : "";
    const sourceMeta = detail.sourceRequest
      ? ` · 来源任务 ${detail.sourceRequest}`
      : "";
    node.querySelector(".proposal-meta").textContent =
      `文件 ${detail.changes.map((change) => change.path).join("、")} · ` +
      `摘要 ${String(detail.digest).slice(0, 19)}… · 过期 ` +
      formatLocalTime(detail.expiresAt) +
      depMeta +
      sourceMeta;

    const awaiting = detail.state === "awaiting-authorization";
    const recovering = detail.state === "recovery-required";
    const applied = detail.state === "applied";
    node.querySelector(".proposal-recovery").hidden = !recovering;
    node.querySelector(".apply-button").hidden = !awaiting;
    node.querySelector(".reject-button").hidden = !awaiting;
    node.querySelector(".revert-button").hidden = !applied;
    node.querySelector(".recover-rollback-button").hidden = !recovering;
    node.querySelector(".recover-finish-button").hidden = !recovering;

    const diffWrap = node.querySelector(".proposal-diff-wrap");
    const diffButton = node.querySelector(".diff-button");
    diffButton.setAttribute("aria-expanded", "false");
    diffButton.addEventListener("click", () => {
      const showing = !diffWrap.hidden;
      if (!showing) {
        node.querySelector(".proposal-diff").textContent = detail.changes
          .map((change) => change.diff || `（无差异：${change.path}）`)
          .join("\n");
      }
      diffWrap.hidden = showing;
      diffButton.setAttribute("aria-expanded", String(!showing));
      diffButton.textContent = showing ? "查看差异" : "收起差异";
    });

    node
      .querySelector(".apply-button")
      .addEventListener("click", () => applyProposal(detail));
    node
      .querySelector(".reject-button")
      .addEventListener("click", () => rejectProposal(detail));
    node
      .querySelector(".revert-button")
      .addEventListener("click", () => revertProposal(detail));
    node
      .querySelector(".recover-rollback-button")
      .addEventListener("click", () => recoverProposal(detail, "rollback"));
    node
      .querySelector(".recover-finish-button")
      .addEventListener("click", () => recoverProposal(detail, "finish"));
    elements.proposalItems.appendChild(fragment);
  }
}

async function proposalVerb(proposal, verb, extra) {
  const body = {
    operation: mutation(newOperationId(), {
      action: verb,
      proposalId: proposal.proposalId,
    }),
    ...(extra || {}),
  };
  return api(
    `/api/v1/projects/${state.proposalsProject.projectId}/actions/proposals/${proposal.proposalId}/${verb}`,
    { method: "POST", body }
  );
}

async function applyProposal(proposal) {
  const confirmed = window.confirm(
    `批准应用该提案？\n\n摘要：${String(proposal.digest).slice(0, 24)}…\n` +
      `文件：${proposal.changes.map((change) => change.path).join("、")}\n\n` +
      "应用前会重查目录、授权、路径与每个文件的基线 hash；任何冲突都不写入。"
  );
  if (!confirmed) {
    announce("已取消应用。");
    return;
  }
  try {
    const outcome = await proposalVerb(proposal, "apply", {
      digest: proposal.digest,
    });
    announce(
      outcome.result.status === "applied"
        ? "提案已应用，结果 hash 已记录。"
        : `提案状态：${outcome.result.status}`
    );
  } catch (error) {
    if (error.code === "recovery-required") {
      announce(
        "写入途中失败：已标记为需要恢复，新的写入被阻止。请选择恢复回滚或恢复完成。"
      );
    } else {
      elements.proposalsError.hidden = false;
      elements.proposalsError.textContent = describeFailure(error, "应用提案");
      announce(elements.proposalsError.textContent);
    }
  }
  await loadProposals();
}

async function rejectProposal(proposal) {
  const confirmed = window.confirm("拒绝该提案？这不会改动任何源文件。");
  if (!confirmed) return;
  try {
    await proposalVerb(proposal, "reject");
    announce("提案已拒绝。");
  } catch (error) {
    elements.proposalsError.hidden = false;
    elements.proposalsError.textContent = describeFailure(error, "拒绝提案");
  }
  await loadProposals();
}

async function revertProposal(proposal) {
  try {
    await proposalVerb(proposal, "revert");
    announce("已生成回退提案（新提案），仍需你批准后才会写回源码。");
  } catch (error) {
    elements.proposalsError.hidden = false;
    elements.proposalsError.textContent = describeFailure(error, "生成回退提案");
  }
  await loadProposals();
}

async function recoverProposal(proposal, mode) {
  const confirmed = window.confirm(
    mode === "rollback"
      ? "恢复回滚：把已写入的文件还原为应用前内容，并删除本次新建的文件？"
      : "恢复完成：继续执行尚未写入的文件变更？"
  );
  if (!confirmed) {
    announce("已取消恢复。");
    return;
  }
  try {
    const outcome = await proposalVerb(proposal, "recover", { mode });
    announce(
      outcome.result.status === "rolled-back"
        ? "已回滚到应用前内容，项目写入已解除阻止。"
        : "恢复完成，本次变更已全部写入。"
    );
  } catch (error) {
    elements.proposalsError.hidden = false;
    elements.proposalsError.textContent =
      error.code === "conflict"
        ? "恢复失败：文件在失败后被外部改动（conflict）。请人工核对，工作台不会覆盖你的修改。"
        : describeFailure(error, "恢复");
    announce(elements.proposalsError.textContent);
  }
  await loadProposals();
}

elements.proposalsClose.addEventListener("click", () => {
  elements.proposalsPanel.hidden = true;
  restorePanelTrigger();
  state.proposalsProject = null;
  announce("已关闭提案面板。");
});

// -- assets: discovery and isolated preview (WB-03) ---------------------

const ASSET_KIND_LABELS = {
  markdown: "Markdown",
  tokens: "Tokens",
  component: "组件（工作台文档）",
  page: "页面（工作台文档）",
  "static-package": "静态页面包",
  "react-source": "React/TS 源码",
  image: "图片",
  "run-artifact": "Run 工件",
  binary: "二进制",
};

const CAPABILITY_LABELS = {
  reference: "参考",
  "static-preview": "静态预览",
  "source-unverified": "未验证源码",
  "runnable-verified": "已运行验证",
  "native-editable": "原生可编辑",
};

const LIFECYCLE_LABELS = {
  draft: "草稿",
  published: "已发布",
  archived: "已归档",
  trashed: "回收站",
};

function labelFor(table, value) {
  return table[value] || value;
}

function capabilityList(capabilities) {
  if (!capabilities || capabilities.length === 0) return "无";
  return capabilities.map((item) => labelFor(CAPABILITY_LABELS, item)).join("、");
}

async function openAssets(project) {
  state.assetsProject = project;
  state.selectedAssetId = null;
  elements.assetDetail.hidden = true;
  elements.assetPreviewFrame.hidden = true;
  elements.assetPreviewFrame.removeAttribute("src");
  elements.assetPreviewNote.textContent = "";
  elements.assetsHeading.textContent = `资产库 · ${project.name}`;
  elements.assetsScope.textContent = `目录：${project.canonicalPath}`;
  elements.assetsPanel.hidden = false;
  elements.assetsError.hidden = true;
  await loadAssets();
  focusIntoPanel(elements.assetsHeading);
}

function assetQueryString() {
  const params = new URLSearchParams();
  const query = elements.assetsQuery.value.trim();
  if (query) params.set("query", query);
  if (elements.assetsKind.value) params.set("kind", elements.assetsKind.value);
  if (elements.assetsCapability.value) {
    params.set("capability", elements.assetsCapability.value);
  }
  const text = params.toString();
  return text ? "?" + text : "";
}

async function loadAssets() {
  const project = state.assetsProject;
  if (!project) return;
  try {
    const listing = await api(
      `/api/v1/projects/${project.projectId}/assets${assetQueryString()}`
    );
    state.assets = listing.assets || [];
    elements.assetsError.hidden = true;
    renderAssets();
  } catch (error) {
    elements.assetsError.hidden = false;
    elements.assetsError.textContent = describeFailure(error, "读取资产");
  }
}

function renderAssets() {
  elements.assetItems.textContent = "";
  elements.assetsEmpty.hidden = state.assets.length > 0;
  for (const asset of state.assets) {
    const fragment = elements.assetTemplate.content.cloneNode(true);
    const node = fragment.querySelector(".asset-item");
    node.dataset.assetId = asset.assetId;
    node.dataset.selected = String(asset.assetId === state.selectedAssetId);
    node.querySelector(".asset-name").textContent = asset.name;
    const matched =
      asset.matchedOn === "tag" ? "（按标签匹配）" : "";
    node.querySelector(".asset-meta").textContent =
      `${labelFor(ASSET_KIND_LABELS, asset.kind)} · ` +
      `${labelFor(LIFECYCLE_LABELS, asset.lifecycle)} · ` +
      `${capabilityList(asset.capabilities)}${matched}`;
    node
      .querySelector(".asset-select")
      .addEventListener("click", () => selectAsset(asset.assetId));
    elements.assetItems.appendChild(fragment);
  }
}

async function selectAsset(assetId) {
  const project = state.assetsProject;
  state.selectedAssetId = assetId;
  renderAssets();
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/assets/${assetId}`
    );
    state.selectedAsset = payload.asset;
    renderAssetDetail(payload.asset);
  } catch (error) {
    elements.assetsError.hidden = false;
    elements.assetsError.textContent = describeFailure(error, "读取资产详情");
  }
}

function renderAssetDetail(asset) {
  elements.assetDetail.hidden = false;
  elements.assetDetailHeading.textContent = asset.name;
  elements.assetDetailKind.textContent = labelFor(ASSET_KIND_LABELS, asset.kind);
  elements.assetDetailLifecycle.textContent = labelFor(
    LIFECYCLE_LABELS,
    asset.lifecycle
  );
  elements.assetDetailCapabilities.textContent = capabilityList(asset.capabilities);
  elements.assetDetailRevision.textContent = asset.revisionNumber
    ? `第 ${asset.revisionNumber} 次发布`
    : "尚未发布（草稿）";
  elements.assetManifest.textContent = "";
  for (const entry of asset.manifest || []) {
    const item = document.createElement("li");
    item.textContent = `${entry.path} · ${entry.mediaType} · ${entry.size} B`;
    elements.assetManifest.appendChild(item);
  }
  elements.assetLocators.textContent = "";
  for (const locator of asset.sourceLocators || []) {
    const item = document.createElement("li");
    item.textContent = `${locator.kind} · ${locator.path} · ${String(
      locator.sourceHash
    ).slice(0, 19)}…`;
    elements.assetLocators.appendChild(item);
  }
  elements.assetWarnings.hidden = !(asset.warnings && asset.warnings.length);
  elements.assetWarnings.textContent = (asset.warnings || []).join(" ");
  elements.assetDesignSystemControls.hidden = asset.kind !== "tokens";
  elements.assetDesignSystemHint.hidden = asset.kind !== "tokens";
  const isDocument = asset.kind === "component" || asset.kind === "page";
  elements.assetDocumentControls.hidden = !isDocument;
  elements.assetDocumentHint.hidden = !isDocument;
  elements.assetOpenDocument.textContent =
    asset.kind === "page" ? "打开页面文档" : "打开组件文档";
  elements.assetPreviewFrame.hidden = true;
  elements.assetPreviewFrame.removeAttribute("src");
  elements.assetPreviewNote.textContent =
    "预览在独立回环来源运行：不带会话凭证、不能访问管理 API 或外网。";
}

async function showAssetPreview(mode) {
  const project = state.assetsProject;
  const asset = state.selectedAsset;
  if (!project || !asset) return;
  try {
    const descriptor = await api(
      `/api/v1/projects/${project.projectId}/assets/${asset.assetId}/preview`
    );
    elements.assetPreviewEnable.hidden =
      descriptor.dynamicAvailable === false || descriptor.dynamicUrl !== null;
    const url = mode === "dynamic" ? descriptor.dynamicUrl : descriptor.staticUrl;
    if (!url) {
      elements.assetPreviewNote.textContent =
        "该资产尚未启用动态预览；静态预览已可用。";
      elements.assetPreviewFrame.hidden = true;
      return;
    }
    elements.assetPreviewFrame.setAttribute(
      "sandbox",
      mode === "dynamic" ? "allow-scripts" : ""
    );
    elements.assetPreviewFrame.setAttribute(
      "src",
      `${url}?type=${encodeURIComponent(descriptor.mediaType)}`
    );
    elements.assetPreviewFrame.hidden = false;
    elements.assetPreviewNote.textContent =
      mode === "dynamic"
        ? "动态预览：脚本已启用，但来源隔离、无凭证、不能联网（限制来自预览来源自身策略）。"
        : "静态预览：脚本已被禁止，仅显示页面结构与样式。";
    announce(elements.assetPreviewNote.textContent);
  } catch (error) {
    elements.assetsError.hidden = false;
    elements.assetsError.textContent = describeFailure(error, "打开预览");
  }
}

async function enableDynamicPreview() {
  const project = state.assetsProject;
  const asset = state.selectedAsset;
  if (!project || !asset) return;
  const confirmed = window.confirm(
    "启用动态预览？预览会执行该资产自身的脚本，但仍在独立来源中运行：" +
      "无会话凭证、不能访问管理 API、不能联网。"
  );
  if (!confirmed) return;
  try {
    await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/preview-enable`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "preview-enable",
            assetId: asset.assetId,
          }),
        },
      }
    );
    await selectAsset(asset.assetId);
    await loadAssets();
    // The descriptor is the authority on whether dynamic preview is now
    // available: re-read it instead of guessing in the UI.
    await showAssetPreview("dynamic");
    announce("已启用动态预览（仍保持隔离与无凭证）。");
  } catch (error) {
    elements.assetsError.hidden = false;
    elements.assetsError.textContent = describeFailure(error, "启用动态预览");
  }
}

elements.assetsFilter.addEventListener("submit", (event) => {
  event.preventDefault();
  loadAssets();
  announce("已应用资产检索条件。");
});
elements.assetsClose.addEventListener("click", () => {
  elements.assetsPanel.hidden = true;
  restorePanelTrigger();
  elements.assetPreviewFrame.hidden = true;
  elements.assetPreviewFrame.removeAttribute("src");
  state.assetsProject = null;
  announce("已关闭资产库。");
});
elements.assetPreviewStatic.addEventListener("click", () => showAssetPreview("static"));
elements.assetPreviewDynamic.addEventListener("click", () =>
  showAssetPreview("dynamic")
);
elements.assetPreviewEnable.addEventListener("click", enableDynamicPreview);
elements.assetDesignSystem.addEventListener("click", () =>
  openDesignSystem(state.selectedAsset)
);
elements.assetOpenDocument.addEventListener("click", () =>
  openDocument(state.selectedAsset)
);

// -- components, layouts, and distill candidates (WB-06) ----------------

const DOCUMENT_VIEWS = { component: "component", page: "page" };
const DOCUMENT_LABELS = {
  component: { title: "组件定义", update: "component-update", publish: "component-publish", hint: "描述、公开属性 schema/default、变体、状态、slot、约束、token/组件依赖与文档。校验不通过不能发布。" },
  page: { title: "页面布局树", update: "page-update", publish: "page-publish", hint: "显式布局树：节点类型、容器关系与实例参数。实例节点必须指向本项目已发布的组件。" },
};

function documentKind(asset) {
  return asset && asset.kind === "page" ? "page" : "component";
}

function documentPath(asset, view) {
  const project = state.documentProject || state.assetsProject;
  return `/api/v1/projects/${project.projectId}/assets/${asset.assetId}/document/${view}`;
}

function showDocumentError(error, action) {
  elements.documentError.hidden = false;
  elements.documentError.textContent = describeFailure(error, action);
}

function renderDocumentValidation(verdict, kind) {
  const errors = verdict.errors || [];
  const names =
    kind === "page" ? verdict.nodeIds || [] : verdict.propNames || [];
  elements.documentValidation.textContent = verdict.valid
    ? `校验通过 · ${names.length} 项`
    : `校验未通过 · ${errors.length} 个问题，发布会被拒绝`;
  elements.documentValidationErrors.textContent = "";
  for (const error of errors) {
    const item = document.createElement("li");
    const detail = error.detail ? ` · ${error.detail}` : "";
    item.textContent = `${error.path} · ${error.kind}${detail}`;
    elements.documentValidationErrors.appendChild(item);
  }
}

async function openDocument(asset) {
  const project = state.assetsProject;
  if (!project || !asset) return;
  state.documentProject = project;
  state.documentAsset = asset;
  const kind = documentKind(asset);
  elements.documentError.hidden = true;
  elements.documentHeading.textContent =
    `${kind === "page" ? "页面" : "组件"} · ${asset.name}`;
  elements.documentScope.textContent =
    `项目：${project.name} · 目录：${project.canonicalPath}`;
  elements.documentEditorTitle.textContent = DOCUMENT_LABELS[kind].title;
  elements.documentEditorHint.textContent = DOCUMENT_LABELS[kind].hint;
  elements.documentStatus.textContent = "";
  elements.documentValidation.textContent = "";
  elements.documentValidationErrors.textContent = "";
  elements.distillResult.textContent = "";
  elements.instanceNote.textContent = "";
  elements.instanceFrame.hidden = true;
  elements.instanceFrame.removeAttribute("src");
  elements.componentInstance.hidden = kind !== "component";
  elements.pageDistill.hidden = kind !== "page";
  elements.documentPanel.hidden = false;
  await loadDocument();
  if (kind === "component") {
    await renderInstance();
  }
  focusIntoPanel(elements.documentHeading);
}

async function loadDocument() {
  const project = state.documentProject;
  const asset = state.documentAsset;
  if (!project || !asset) return;
  const kind = documentKind(asset);
  try {
    const payload = await api(documentPath(asset, DOCUMENT_VIEWS[kind]));
    const text = kind === "page" ? payload.layout : payload.definition;
    elements.documentText.value = JSON.stringify(text, null, 2);
    renderDocumentValidation(payload.validation, kind);
    const source = payload.source || {};
    elements.documentStatus.textContent =
      source.kind === "revision"
        ? `文档来自第 ${source.revisionNumber} 次发布的修订。`
        : "文档来自草稿（尚未发布）。";
  } catch (error) {
    showDocumentError(error, "读取文档");
  }
}

function parsedDocumentField(kind) {
  const raw = JSON.parse(elements.documentText.value);
  return kind === "page" ? { layout: raw } : { definition: raw };
}

async function saveDocument() {
  const project = state.documentProject;
  const asset = state.documentAsset;
  if (!project || !asset) return;
  const kind = documentKind(asset);
  let fields;
  try {
    fields = parsedDocumentField(kind);
  } catch (error) {
    // A local parse failure never becomes a request.
    elements.documentValidation.textContent = "本地 JSON 解析失败，未发送任何请求";
    elements.documentValidationErrors.textContent = "";
    const item = document.createElement("li");
    item.textContent = `JSON 解析错误：${error.message}`;
    elements.documentValidationErrors.appendChild(item);
    announce("文档不是合法 JSON，未保存。");
    return;
  }
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/${DOCUMENT_LABELS[kind].update}`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: DOCUMENT_LABELS[kind].update,
            assetId: asset.assetId,
          }),
          ...fields,
        },
      }
    );
    elements.documentError.hidden = true;
    renderDocumentValidation(payload.result.validation, kind);
    elements.documentStatus.textContent =
      "草稿已保存并通过校验；发布新版本后才会成为固定修订。";
    announce("文档草稿已保存。");
    await loadAssets();
  } catch (error) {
    showDocumentError(error, "保存文档草稿");
    await loadDocument();
  }
}

async function publishDocument() {
  const project = state.documentProject;
  const asset = state.documentAsset;
  if (!project || !asset) return;
  const kind = documentKind(asset);
  const verb = DOCUMENT_LABELS[kind].publish;
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/${verb}`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: verb,
            assetId: asset.assetId,
          }),
        },
      }
    );
    elements.documentError.hidden = true;
    renderDocumentValidation(payload.result.validation, kind);
    elements.documentStatus.textContent =
      `已发布第 ${payload.result.revisionNumber} 次修订。`;
    announce(`已发布第 ${payload.result.revisionNumber} 次修订。`);
    await loadAssets();
  } catch (error) {
    showDocumentError(error, "发布文档修订");
    await loadDocument();
  }
}

async function renderInstance() {
  const project = state.documentProject;
  const asset = state.documentAsset;
  if (!project || !asset) return;
  let params;
  try {
    const raw = elements.instanceParams.value.trim();
    params = raw ? JSON.parse(raw) : {};
  } catch (error) {
    elements.instanceNote.textContent = `参数不是合法 JSON：${error.message}`;
    elements.instanceFrame.hidden = true;
    return;
  }
  try {
    const query = params && Object.keys(params).length
      ? `?params=${encodeURIComponent(JSON.stringify(params))}`
      : "";
    const payload = await api(documentPath(asset, "instance") + query);
    elements.documentError.hidden = true;
    elements.instanceVariants.textContent =
      (payload.declared.variants || []).join("、") || "未声明";
    elements.instanceStates.textContent =
      (payload.declared.states || []).join("、") || "未声明";
    elements.instanceSlots.textContent =
      (payload.declared.slots || []).join("、") || "未声明";
    const unresolved = payload.unsetParams || [];
    elements.instanceNote.textContent =
      `${payload.limitations} 未赋值且无默认值的属性：${unresolved.length ? unresolved.join("、") : "无"}。`;
    elements.instanceFrame.setAttribute("sandbox", "");
    elements.instanceFrame.setAttribute("src", payload.previewUrl);
    elements.instanceFrame.hidden = false;
    announce("已渲染组件样例。");
  } catch (error) {
    elements.instanceNote.textContent = "";
    showDocumentError(error, "渲染组件样例");
  }
}

async function createDocument(kind) {
  const project = state.assetsProject;
  if (!project) return;
  const count = (state.assets || []).filter(
    (asset) => asset.kind === kind
  ).length;
  const name = kind === "page" ? `新页面 ${count + 1}` : `新组件 ${count + 1}`;
  const template = kind === "page" ? PAGE_TEMPLATE(name) : COMPONENT_TEMPLATE(name);
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/${kind === "page" ? "pages" : "components"}`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), { action: kind === "page" ? "pages" : "components", name }),
          name,
          ...(kind === "page" ? { layout: template } : { definition: template }),
        },
      }
    );
    elements.assetsError.hidden = true;
    await loadAssets();
    await openDocument(payload.result);
    announce(`已创建${kind === "page" ? "页面" : "组件"}文档。`);
  } catch (error) {
    elements.assetsError.hidden = false;
    elements.assetsError.textContent = describeFailure(error, "新建文档");
  }
}

function COMPONENT_TEMPLATE(name) {
  return {
    name,
    description: "",
    props: [{ name: "label", type: "string", default: "确定" }],
    variants: [],
    states: [],
    slots: [],
    constraints: {},
    dependencies: { tokens: [], components: [] },
  };
}

function PAGE_TEMPLATE(name) {
  return {
    name,
    nodes: [
      { id: "root", type: "stack", children: ["title"], props: { direction: "vertical" } },
      { id: "title", type: "text", props: { text: "标题" } },
    ],
  };
}

async function distillCandidate(event) {
  event.preventDefault();
  const project = state.documentProject;
  const asset = state.documentAsset;
  if (!project || !asset) return;
  const nodeIds = elements.distillNodes.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const name = elements.distillName.value.trim();
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/distill-candidate`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "distill-candidate",
            assetId: asset.assetId,
            nodeIds,
          }),
          sourcePageAssetId: asset.assetId,
          nodeIds,
          ...(name ? { name } : {}),
        },
      }
    );
    const result = payload.result;
    elements.documentError.hidden = true;
    elements.distillResult.textContent =
      `候选 ${result.assetId} 已创建（草稿，complete=${result.candidate.complete}）：` +
      `需补全公开参数与依赖后才能发布。`;
    announce("已生成提炼候选组件。");
    await loadAssets();
  } catch (error) {
    elements.distillResult.textContent = "";
    showDocumentError(error, "生成提炼候选");
  }
}

elements.createComponent.addEventListener("click", () => createDocument("component"));
elements.createPage.addEventListener("click", () => createDocument("page"));
elements.documentSave.addEventListener("click", saveDocument);
elements.documentPublish.addEventListener("click", publishDocument);
elements.documentReload.addEventListener("click", loadDocument);
elements.instanceRender.addEventListener("click", renderInstance);
elements.distillForm.addEventListener("submit", distillCandidate);
elements.documentClose.addEventListener("click", () => {
  elements.documentPanel.hidden = true;
  restorePanelTrigger();
  elements.instanceFrame.hidden = true;
  elements.instanceFrame.removeAttribute("src");
  state.documentProject = null;
  state.documentAsset = null;
  announce("已关闭组件与页面文档。");
});

// -- design system: typed tokens, themes, baseline proposal (WB-05) -----

const TOKEN_ERROR_LABELS = {
  "missing-reference": "缺失引用",
  "reference-cycle": "引用循环",
  "type-mismatch": "类型不符",
  "invalid-value": "取值非法",
  "invalid-reference": "引用写法无效",
};

function tokenErrorLabel(kind) {
  return TOKEN_ERROR_LABELS[kind] || kind;
}

function showTokensError(error, action) {
  elements.tokensError.hidden = false;
  elements.tokensError.textContent = describeFailure(error, action);
}

function tokensPath(suffix) {
  const project = state.tokensProject;
  const asset = state.tokensAsset;
  return `/api/v1/projects/${project.projectId}/assets/${asset.assetId}/tokens/${suffix}`;
}

async function openDesignSystem(asset) {
  const project = state.assetsProject;
  if (!project || !asset) return;
  state.tokensProject = project;
  state.tokensAsset = asset;
  elements.tokensError.hidden = true;
  elements.tokensHeading.textContent = `设计系统 · ${asset.name}`;
  elements.tokensScope.textContent =
    `项目：${project.name} · 目录：${project.canonicalPath}`;
  const manifest = asset.manifest || [];
  elements.tokensBaselinePath.value = manifest.length ? manifest[0].path : "";
  elements.tokensBaselineResult.textContent = "";
  elements.tokensStatus.textContent = "";
  elements.tokensValidation.textContent = "";
  elements.tokensValidationErrors.textContent = "";
  elements.tokensDiffCounts.textContent = "";
  elements.tokensDiff.textContent = "";
  elements.tokensAffectedNote.textContent = "";
  elements.tokensAffected.textContent = "";
  elements.tokensPreviewNote.textContent = "";
  elements.tokensPreviewFrame.hidden = true;
  elements.tokensPreviewFrame.removeAttribute("src");
  elements.tokensPanel.hidden = false;
  await loadTokenDocument();
  await loadTokenValidation();
  await loadTokenAffected();
  focusIntoPanel(elements.tokensHeading);
}

async function loadTokenDocument() {
  try {
    const payload = await api(tokensPath("document"));
    elements.tokensDocument.value = payload.text;
    renderThemeOptions(payload.themes || []);
    const source = payload.source || {};
    elements.tokensStatus.textContent =
      source.kind === "revision"
        ? `编辑器内容来自第 ${source.revisionNumber} 次发布的修订；它不会随源文件改动而变。`
        : "编辑器内容来自草稿（尚未发布）。";
  } catch (error) {
    showTokensError(error, "读取 tokens 文档");
  }
}

function renderThemeOptions(themes) {
  const previous = elements.tokensTheme.value;
  elements.tokensTheme.textContent = "";
  const fallback = document.createElement("option");
  fallback.value = "";
  fallback.textContent = "默认（不加主题）";
  elements.tokensTheme.appendChild(fallback);
  for (const theme of themes) {
    const option = document.createElement("option");
    option.value = theme;
    option.textContent = theme;
    elements.tokensTheme.appendChild(option);
  }
  if (previous && themes.includes(previous)) {
    elements.tokensTheme.value = previous;
  } else if (previous) {
    // The stored document no longer declares that theme: drop the sample
    // instead of leaving a picture that no longer matches the tokens.
    elements.tokensPreviewFrame.hidden = true;
    elements.tokensPreviewFrame.removeAttribute("src");
    elements.tokensPreviewNote.textContent = `当前文档已不再声明主题 ${previous}，样例已收起。`;
  }
}

function renderTokenValidation(verdict) {
  const errors = verdict.errors || [];
  renderThemeOptions(verdict.themes || []);
  elements.tokensValidation.textContent = verdict.valid
    ? `校验通过 · ${verdict.tokenCount} 个 token · 分类：${(verdict.categories || []).join("、")}`
    : `校验未通过 · ${errors.length} 个问题，发布会被拒绝`;
  elements.tokensValidationErrors.textContent = "";
  for (const error of errors) {
    const item = document.createElement("li");
    const target = error.target ? ` → ${error.target}` : "";
    item.textContent = `${error.path} · ${tokenErrorLabel(error.kind)}${target}`;
    elements.tokensValidationErrors.appendChild(item);
  }
}

async function loadTokenValidation() {
  try {
    const verdict = await api(tokensPath("validation"));
    renderTokenValidation(verdict);
    return verdict;
  } catch (error) {
    elements.tokensValidation.textContent = "";
    elements.tokensValidationErrors.textContent = "";
    showTokensError(error, "读取 tokens 校验结果");
    return null;
  }
}

async function loadTokenAffected() {
  try {
    const payload = await api(tokensPath("affected"));
    elements.tokensAffectedNote.textContent = payload.note || "";
    elements.tokensAffected.textContent = "";
    for (const entry of payload.components || []) {
      const item = document.createElement("li");
      item.textContent =
        `组件 ${entry.name}（${entry.kind}）· 固定在第 ${entry.revisionNumber} 次修订`;
      elements.tokensAffected.appendChild(item);
    }
    for (const entry of payload.instances || []) {
      const item = document.createElement("li");
      item.textContent = `实例 ${entry.instanceId} · 资产 ${entry.assetId}`;
      elements.tokensAffected.appendChild(item);
    }
    if (elements.tokensAffected.children.length === 0) {
      const item = document.createElement("li");
      item.textContent = "当前没有已登记的引用。";
      elements.tokensAffected.appendChild(item);
    }
  } catch (error) {
    showTokensError(error, "读取受影响的引用");
  }
}

function tokensMutation(payload) {
  return mutation(newOperationId(), {
    action: "tokens-update",
    assetId: state.tokensAsset.assetId,
    ...payload,
  });
}

async function saveTokenDraft() {
  const project = state.tokensProject;
  const asset = state.tokensAsset;
  if (!project || !asset) return;
  let parsed;
  try {
    parsed = JSON.parse(elements.tokensDocument.value);
  } catch (error) {
    // A local parse failure never becomes a request: the maintainer sees
    // the real parser message next to the editor.
    elements.tokensValidation.textContent = "本地 JSON 解析失败，未发送任何请求";
    elements.tokensValidationErrors.textContent = "";
    const item = document.createElement("li");
    item.textContent = `JSON 解析错误：${error.message}`;
    elements.tokensValidationErrors.appendChild(item);
    announce("tokens 文档不是合法 JSON，未保存。");
    return;
  }
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/tokens-update`,
      { method: "POST", body: { operation: tokensMutation({ document: parsed }), document: parsed } }
    );
    renderTokenValidation(payload.result.validation);
    elements.tokensError.hidden = true;
    elements.tokensStatus.textContent =
      "草稿已保存并通过校验；发布新版本后才会成为固定修订。";
    announce("tokens 草稿已保存。");
  } catch (error) {
    showTokensError(error, "保存 tokens 草稿");
    await loadTokenValidation();
  }
}

async function publishTokens() {
  const project = state.tokensProject;
  const asset = state.tokensAsset;
  if (!project || !asset) return;
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/tokens-publish`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "tokens-publish",
            assetId: asset.assetId,
          }),
        },
      }
    );
    const result = payload.result;
    elements.tokensError.hidden = true;
    renderTokenValidation(result.validation);
    elements.tokensStatus.textContent =
      `已发布第 ${result.revisionNumber} 次修订；引用与项目基线都不会自动升级。`;
    announce(`已发布第 ${result.revisionNumber} 次 tokens 修订。`);
    await loadTokenAffected();
  } catch (error) {
    showTokensError(error, "发布 tokens 修订");
    await loadTokenValidation();
  }
}

async function renderTokenPreview() {
  const project = state.tokensProject;
  const asset = state.tokensAsset;
  if (!project || !asset) return;
  const theme = elements.tokensTheme.value;
  try {
    const query = theme ? `?theme=${encodeURIComponent(theme)}` : "";
    const payload = await api(tokensPath("preview") + query);
    elements.tokensError.hidden = true;
    elements.tokensPreviewFrame.setAttribute("sandbox", "");
    elements.tokensPreviewFrame.setAttribute("src", payload.previewUrl);
    elements.tokensPreviewFrame.hidden = false;
    elements.tokensPreviewNote.textContent =
      `样例由同一份 token 解析结果渲染 · 主题：${payload.theme || "默认"} · ` +
      "独立回环来源，无凭证、无管理 API、无外网。";
    announce("已渲染设计系统样例。");
  } catch (error) {
    showTokensError(error, "渲染样例预览");
  }
}

async function loadTokenDiff() {
  try {
    const payload = await api(tokensPath("diff"));
    elements.tokensError.hidden = true;
    elements.tokensDiffCounts.textContent =
      `第 ${payload.from.revisionNumber} 次 → 第 ${payload.to.revisionNumber} 次修订：` +
      `变更 ${payload.counts.changed} · 新增 ${payload.counts.added} · 删除 ${payload.counts.removed}`;
    elements.tokensDiff.textContent = "";
    for (const entry of payload.changed) {
      const item = document.createElement("li");
      item.textContent = `${entry.path}：${entry.from} → ${entry.to}`;
      elements.tokensDiff.appendChild(item);
    }
    for (const entry of payload.added) {
      const item = document.createElement("li");
      item.textContent = `${entry.path}：新增 ${entry.value}`;
      elements.tokensDiff.appendChild(item);
    }
    for (const entry of payload.removed) {
      const item = document.createElement("li");
      item.textContent = `${entry.path}：删除（原 ${entry.value}）`;
      elements.tokensDiff.appendChild(item);
    }
    if (elements.tokensDiff.children.length === 0) {
      const item = document.createElement("li");
      item.textContent = "两次修订之间没有差异。";
      elements.tokensDiff.appendChild(item);
    }
  } catch (error) {
    elements.tokensDiff.textContent = "";
    if (error.status === 422) {
      // A missing comparison is not an error the maintainer must fix here.
      elements.tokensDiffCounts.textContent =
        "还没有两个可比较的修订；先发布两次修订再比较。";
      return;
    }
    showTokensError(error, "比较版本差异");
  }
}

async function proposeBaseline(event) {
  event.preventDefault();
  const project = state.tokensProject;
  const asset = state.tokensAsset;
  if (!project || !asset) return;
  const path = elements.tokensBaselinePath.value.trim();
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/propose-baseline`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "propose-baseline",
            assetId: asset.assetId,
            path,
          }),
          path,
        },
      }
    );
    const proposal = payload.result;
    elements.tokensError.hidden = true;
    elements.tokensBaselineResult.textContent =
      `提案 ${proposal.proposalId} 状态：${proposalStateLabel(proposal.state)} · ` +
      `目标 ${proposal.changes[0].path}。请到“变更提案”面板复核 diff 并授权；` +
      "本操作没有写入项目文件。";
    announce("已生成基线替换提案，等待维护者授权。");
  } catch (error) {
    elements.tokensBaselineResult.textContent = "";
    showTokensError(error, "生成基线替换提案");
  }
}

elements.tokensSave.addEventListener("click", saveTokenDraft);
elements.tokensPublish.addEventListener("click", publishTokens);
elements.tokensReload.addEventListener("click", loadTokenDocument);
elements.tokensPreviewRefresh.addEventListener("click", renderTokenPreview);
elements.tokensDiffButton.addEventListener("click", loadTokenDiff);
elements.tokensBaselineForm.addEventListener("submit", proposeBaseline);
elements.tokensClose.addEventListener("click", () => {
  elements.tokensPanel.hidden = true;
  restorePanelTrigger();
  elements.tokensPreviewFrame.hidden = true;
  elements.tokensPreviewFrame.removeAttribute("src");
  state.tokensProject = null;
  state.tokensAsset = null;
  announce("已关闭设计系统。");
});

// -- canvas: boards, gestures, throttled save, undo (WB-07) -------------

const CANVAS_SAVE_DEBOUNCE_MS = 500;
const CANVAS_SAVE_DEADLINE_MS = 2000;

function canvasPath(suffix) {
  const project = state.canvasProject;
  return `/api/v1/projects/${project.projectId}/canvases${suffix}`;
}

function canvasActionPath(verb) {
  const project = state.canvasProject;
  return (
    `/api/v1/projects/${project.projectId}/actions/canvases/` +
    `${state.canvas.canvasId}/${verb}`
  );
}

function activeBoard() {
  const doc = state.canvasDocument;
  if (!doc) return null;
  return (
    (doc.boards || []).find((board) => board.id === state.canvasBoardId) ||
    (doc.boards || [])[0] ||
    null
  );
}

function selectedNodes() {
  const board = activeBoard();
  if (!board) return [];
  return board.nodes.filter((node) => state.canvasSelection.includes(node.id));
}

function setCanvasSaveState(kind, message) {
  state.canvasSaveState = kind;
  const labels = {
    idle: "未载入画布",
    saved: "已保存（服务已确认）",
    dirty: "有未保存编辑…",
    saving: "保存中…",
    failed: "保存失败：编辑仍在内存中，可重试或另存分支",
    conflict: "保存冲突：另一处已写入，本页草稿未覆盖它",
  };
  elements.canvasSaveState.textContent = message || labels[kind] || kind;
  elements.canvasRetry.hidden = kind !== "failed";
  elements.canvasFork.hidden = kind !== "conflict";
  elements.canvasDirtyNote.hidden = !(kind === "failed" || kind === "conflict");
}

function showCanvasError(error, action) {
  elements.canvasError.hidden = false;
  elements.canvasError.textContent = describeFailure(error, action);
}

// -- local draft mirror (the server stays authoritative) ----------------

function applyLocalCommand(command) {
  const doc = state.canvasDocument;
  if (!doc) return;
  const board = (doc.boards || []).find((item) => item.id === command.boardId);
  const nodeOf = (id) => board && board.nodes.find((item) => item.id === id);
  if (command.kind === "board-add") {
    doc.boards.push({
      id: command.boardId,
      name: command.name,
      width: command.width || 1200,
      height: command.height || 800,
      background: "",
      nodes: [],
      flowEdges: [],
    });
  } else if (command.kind === "board-rename" && board) {
    board.name = command.name;
  } else if (command.kind === "board-resize" && board) {
    board.width = command.width;
    board.height = command.height;
  } else if (command.kind === "node-add" && board) {
    board.nodes.push(command.node);
  } else if (command.kind === "node-move" && board) {
    for (const id of command.nodeIds) {
      const node = nodeOf(id);
      if (!node) continue;
      node.layout.x = Math.round((node.layout.x + command.dx) * 1000) / 1000;
      node.layout.y = Math.round((node.layout.y + command.dy) * 1000) / 1000;
    }
  } else if (command.kind === "node-resize" && board) {
    const node = nodeOf(command.nodeId);
    if (node) Object.assign(node.layout, command.layout);
  } else if (command.kind === "node-delete" && board) {
    board.nodes = board.nodes.filter((node) => !command.nodeIds.includes(node.id));
    for (const node of board.nodes) {
      node.children = (node.children || []).filter(
        (child) => !command.nodeIds.includes(child)
      );
    }
  } else if (command.kind === "node-duplicate" && board) {
    command.newIds = command.nodeIds.map((id) => {
      const source = nodeOf(id);
      const clone = JSON.parse(JSON.stringify(source));
      clone.id = `n_${Math.random().toString(16).slice(2, 14)}`;
      clone.layout.x += 16;
      clone.layout.y += 16;
      clone.layout.z = board.nodes.length;
      board.nodes.push(clone);
      return clone.id;
    });
  } else if (command.kind === "node-props" && board) {
    const node = nodeOf(command.nodeId);
    if (node) node.props = { ...node.props, ...command.props };
  } else if (command.kind === "instance-params" && board) {
    const node = nodeOf(command.nodeId);
    if (node) node.props = { ...node.props, params: command.params };
  } else if (command.kind === "node-group" && board) {
    const selected = command.nodeIds;
    const nodes = selected.map(nodeOf).filter(Boolean);
    if (nodes.length) {
      const xs = nodes.map((node) => node.layout.x);
      const ys = nodes.map((node) => node.layout.y);
      const group = {
        id: `n_${Math.random().toString(16).slice(2, 14)}`,
        type: "container",
        children: [...selected],
        props: { label: "分组" },
        layout: {
          x: Math.min(...xs),
          y: Math.min(...ys),
          width: 320,
          height: 200,
          z: Math.max(...nodes.map((node) => node.layout.z || 0)),
        },
      };
      for (const node of board.nodes) {
        if (selected.includes(node.id)) continue;
        node.children = (node.children || []).filter(
          (child) => !selected.includes(child)
        );
      }
      command.groupId = group.id;
      board.nodes.push(group);
    }
  }
}

// -- command queue with 500 ms debounce / 2 s deadline -------------------

function queueCanvasCommand(command, options) {
  applyLocalCommand(command);
  state.canvasQueue.push(command);
  if (options && options.selectCreated) {
    const created = command.newIds || (command.groupId ? [command.groupId] : null);
    if (created) state.canvasSelection = [...created];
  }
  if (state.canvasSaveState === "saved") setCanvasSaveState("dirty");
  scheduleCanvasFlush();
  renderCanvas();
}

function scheduleCanvasFlush() {
  if (state.canvasTimers.debounce !== null) {
    window.clearTimeout(state.canvasTimers.debounce);
  }
  state.canvasTimers.debounce = window.setTimeout(
    () => flushCanvasQueue(),
    CANVAS_SAVE_DEBOUNCE_MS
  );
  if (state.canvasTimers.deadline === null) {
    // Continuous editing still commits at most every 2 s (R09).
    state.canvasTimers.deadline = window.setTimeout(
      () => flushCanvasQueue(),
      CANVAS_SAVE_DEADLINE_MS
    );
  }
}

function clearCanvasTimers() {
  if (state.canvasTimers.debounce !== null) {
    window.clearTimeout(state.canvasTimers.debounce);
    state.canvasTimers.debounce = null;
  }
  if (state.canvasTimers.deadline !== null) {
    window.clearTimeout(state.canvasTimers.deadline);
    state.canvasTimers.deadline = null;
  }
}

async function flushCanvasQueue() {
  clearCanvasTimers();
  if (!state.canvas || state.canvasQueue.length === 0) return;
  const commands = state.canvasQueue.splice(0, state.canvasQueue.length);
  // Local mirror fields never leave the page: the server rejects unknown
  // command fields, which is what keeps the two sides honest.
  const wire = commands.map((command) => ({ ...command }));
  setCanvasSaveState("saving");
  try {
    const payload = await api(canvasActionPath("commands"), {
      method: "POST",
      body: {
        operation: mutation(
          newOperationId(),
          { action: "commands", canvasId: state.canvas.canvasId, commands: wire },
          state.canvasCounter
        ),
        commands: wire,
      },
    });
    adoptCanvasPayload(payload);
    setCanvasSaveState("saved");
  } catch (error) {
    // The draft stays in memory: nothing here claims it was saved.
    if (state.canvasQueue.length === 0) state.canvasQueue = commands;
    if (error.status === 409) {
      setCanvasSaveState("conflict");
      elements.canvasError.hidden = false;
      elements.canvasError.textContent =
        "保存冲突：另一窗口或 Agent 已写入该画布。本页草稿未被覆盖，可另存分支。";
      return;
    }
    setCanvasSaveState("failed");
    showCanvasError(error, "保存画布编辑");
  }
}

function adoptCanvasPayload(envelope) {
  // Mutation responses carry the payload under `result` and the confirmed
  // counter at the envelope level: reading the wrong level would leave the
  // window on a stale counter and make every later save a conflict.
  const payload = envelope.result || envelope;
  if (payload.canvas) state.canvas = payload.canvas;
  if (typeof envelope.counter === "number") state.canvasCounter = envelope.counter;
  else if (payload.canvas) state.canvasCounter = payload.canvas.counter;
  if (payload.document) {
    state.canvasDocument = payload.document;
    // Commands queued while this request was in flight stay applied on top
    // of the confirmed document.
    for (const pending of state.canvasQueue) applyLocalCommand(pending);
  }
  if (payload.history) state.canvasHistory = payload.history;
  renderCanvas();
}

function canvasHasUnsavedEdits() {
  return state.canvasQueue.length > 0 || state.canvasSaveState === "failed";
}

window.addEventListener("beforeunload", (event) => {
  if (!state.canvas || !canvasHasUnsavedEdits()) return;
  event.preventDefault();
  event.returnValue = "画布还有未确认的编辑。";
});

// -- rendering -----------------------------------------------------------

function renderCanvas() {
  const doc = state.canvasDocument;
  if (!doc) return;
  const boards = doc.boards || [];
  elements.canvasBoardSelect.textContent = "";
  for (const board of boards) {
    const option = document.createElement("option");
    option.value = board.id;
    option.textContent = board.name;
    option.selected = board.id === state.canvasBoardId;
    elements.canvasBoardSelect.appendChild(option);
  }
  const board = activeBoard();
  elements.canvasStage.textContent = "";
  if (!board) return;
  elements.canvasStage.style.width = board.width + "px";
  elements.canvasStage.style.height = board.height + "px";
  elements.canvasStage.style.background = board.background || "var(--canvas-stage-bg)";
  elements.canvasStage.style.transform =
    `translate(${state.canvasView.x}px, ${state.canvasView.y}px) ` +
    `scale(${state.canvasView.scale})`;
  const ordered = [...board.nodes].sort(
    (left, right) => (left.layout.z || 0) - (right.layout.z || 0)
  );
  for (const node of ordered) {
    const box = document.createElement("div");
    box.className = "canvas-node canvas-node-" + node.type;
    box.dataset.nodeId = node.id;
    box.dataset.selected = String(state.canvasSelection.includes(node.id));
    box.style.left = node.layout.x + "px";
    box.style.top = node.layout.y + "px";
    box.style.width = node.layout.width + "px";
    box.style.height = node.layout.height + "px";
    box.style.zIndex = String(node.layout.z || 0);
    box.tabIndex = 0;
    const label = document.createElement("span");
    label.className = "canvas-node-label";
    label.textContent = canvasNodeLabel(node);
    box.appendChild(label);
    const handle = document.createElement("span");
    handle.className = "canvas-resize-handle";
    handle.title = "拖动缩放";
    box.appendChild(handle);
    elements.canvasStage.appendChild(box);
  }
  renderCanvasSelection();
  renderCanvasProps();
  renderFlows();
  renderScheme();
  elements.canvasUndo.disabled = !state.canvasHistory.canUndo;
  elements.canvasRedo.disabled = !state.canvasHistory.canRedo;
}

function canvasNodeLabel(node) {
  const props = node.props || {};
  if (node.type === "text") return props.text || "文本";
  if (node.type === "link" || node.type === "button") return props.label || node.type;
  if (node.type === "image") return props.source || "图片";
  if (node.type === "slot") return "slot " + (props.name || "");
  if (node.type === "instance") {
    const instance = state.canvasInstances.get(props.instanceId);
    const revision = instance ? `第 ${instance.revisionNumber ?? "?"} 次修订` : "实例";
    return `实例 · ${revision} · 参数 ${Object.keys(props.params || {}).length} 项`;
  }
  return props.label || node.type;
}

function renderCanvasSelection() {
  const nodes = selectedNodes();
  if (nodes.length === 0) {
    elements.canvasSelection.textContent = "未选择任何节点";
  } else if (nodes.length === 1) {
    elements.canvasSelection.textContent = `已选择 ${nodes[0].type} 节点`;
  } else {
    elements.canvasSelection.textContent = `已选择 ${nodes.length} 个节点`;
  }
}

function renderCanvasProps() {
  const board = activeBoard();
  const nodes = selectedNodes();
  const node = nodes.length === 1 ? nodes[0] : null;
  elements.canvasNodeProps.hidden = node === null;
  elements.canvasBoardProps.hidden = board === null;
  if (node) {
    elements.propX.value = node.layout.x;
    elements.propY.value = node.layout.y;
    elements.propWidth.value = node.layout.width;
    elements.propHeight.value = node.layout.height;
    const content = canvasContentField(node);
    elements.propContentLabel.textContent = content.label;
    elements.propContent.value = content.value;
    elements.propToken.value = node.props.tokenRef || "";
  }
  if (board) {
    elements.boardWidth.value = board.width;
    elements.boardHeight.value = board.height;
  }
  const instance = node && node.type === "instance" ? node : null;
  elements.canvasInstanceProps.hidden = instance === null;
  if (instance) {
    const row = state.canvasInstances.get(instance.props.instanceId);
    elements.canvasInstanceInfo.textContent = row
      ? `实例 ${instance.props.instanceId} · 资产 ${row.assetId} · 当前第 ${
          row.revisionNumber ?? "?"
        } 次修订`
      : `实例 ${instance.props.instanceId} 不在本项目实例清单中（发布或授权可能已变化）。`;
    elements.canvasInstanceParams.value = JSON.stringify(
      instance.props.params || {},
      null,
      2
    );
    elements.canvasInstanceUpgrade.disabled = !row;
  }
}

// -- view transforms -----------------------------------------------------

function setCanvasZoom(scale) {
  state.canvasView.scale = Math.min(3, Math.max(0.2, scale));
  elements.canvasZoomLabel.textContent = Math.round(state.canvasView.scale * 100) + "%";
  renderCanvas();
}

function fitCanvasView() {
  const board = activeBoard();
  if (!board) return;
  const box = elements.canvasViewport.getBoundingClientRect();
  if (box.width < 40 || box.height < 40) return;
  const scale = Math.min(
    2,
    Math.max(
      0.2,
      Math.min((box.width - 40) / board.width, (box.height - 40) / board.height)
    )
  );
  state.canvasView.scale = scale;
  state.canvasView.x = Math.max(16, (box.width - board.width * scale) / 2);
  state.canvasView.y = Math.max(16, (box.height - board.height * scale) / 2);
  elements.canvasZoomLabel.textContent = Math.round(scale * 100) + "%";
  renderCanvas();
}

// -- pointer gestures: one gesture is one transaction --------------------

function canvasPoint(event) {
  const stage = elements.canvasStage.getBoundingClientRect();
  return {
    x: (event.clientX - stage.left) / state.canvasView.scale,
    y: (event.clientY - stage.top) / state.canvasView.scale,
  };
}

let canvasGesture = null;

function beginCanvasGesture(event) {
  if (event.button !== 0) return;
  const board = activeBoard();
  if (!board) return;
  const target = event.target.closest(".canvas-node");
  if (!target) {
    if (event.altKey) {
      canvasGesture = { kind: "pan", startX: event.clientX, startY: event.clientY };
      elements.canvasViewport.dataset.panning = "true";
    } else {
      canvasGesture = { kind: "box", start: canvasPoint(event) };
    }
    elements.canvasViewport.setPointerCapture(event.pointerId);
    return;
  }
  // Suppress native pointer focus on the node replaced by renderCanvas().
  event.preventDefault();
  elements.canvasViewport.focus({ preventScroll: true });
  const nodeId = target.dataset.nodeId;
  const additive = event.shiftKey || event.metaKey || event.ctrlKey;
  if (additive && !state.canvasSelection.includes(nodeId)) {
    state.canvasSelection = [...state.canvasSelection, nodeId];
  } else if (!state.canvasSelection.includes(nodeId)) {
    state.canvasSelection = [nodeId];
  }
  renderCanvas();
  if (event.target.classList.contains("canvas-resize-handle")) {
    const node = selectedNodes()[0];
    canvasGesture = node
      ? {
          kind: "resize",
          nodeId: node.id,
          start: canvasPoint(event),
          origin: { ...node.layout },
        }
      : null;
  } else {
    canvasGesture = {
      kind: "move",
      start: canvasPoint(event),
      origins: selectedNodes().map((node) => ({
        id: node.id,
        layout: { ...node.layout },
      })),
    };
  }
  if (canvasGesture) elements.canvasViewport.setPointerCapture(event.pointerId);
}

function updateCanvasGesture(event) {
  if (!canvasGesture) return;
  const board = activeBoard();
  if (!board) return;
  if (canvasGesture.kind === "pan") {
    state.canvasView.x += event.clientX - canvasGesture.startX;
    state.canvasView.y += event.clientY - canvasGesture.startY;
    canvasGesture.startX = event.clientX;
    canvasGesture.startY = event.clientY;
    renderCanvas();
    return;
  }
  if (canvasGesture.kind === "box") {
    const current = canvasPoint(event);
    const box = {
      x: Math.min(canvasGesture.start.x, current.x),
      y: Math.min(canvasGesture.start.y, current.y),
      width: Math.abs(current.x - canvasGesture.start.x),
      height: Math.abs(current.y - canvasGesture.start.y),
    };
    let overlay = elements.canvasStage.querySelector(".canvas-box");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "canvas-box";
      elements.canvasStage.appendChild(overlay);
    }
    overlay.style.left = box.x + "px";
    overlay.style.top = box.y + "px";
    overlay.style.width = box.width + "px";
    overlay.style.height = box.height + "px";
    return;
  }
  const point = canvasPoint(event);
  if (canvasGesture.kind === "move") {
    const dx = Math.round((point.x - canvasGesture.start.x) * 100) / 100;
    const dy = Math.round((point.y - canvasGesture.start.y) * 100) / 100;
    for (const origin of canvasGesture.origins) {
      const node = board.nodes.find((item) => item.id === origin.id);
      if (!node) continue;
      node.layout.x = Math.round((origin.layout.x + dx) * 1000) / 1000;
      node.layout.y = Math.round((origin.layout.y + dy) * 1000) / 1000;
    }
    renderCanvas();
    return;
  }
  if (canvasGesture.kind === "resize") {
    const node = board.nodes.find((item) => item.id === canvasGesture.nodeId);
    if (!node) return;
    node.layout.width = Math.max(
      8,
      Math.round(canvasGesture.origin.width + (point.x - canvasGesture.start.x))
    );
    node.layout.height = Math.max(
      8,
      Math.round(canvasGesture.origin.height + (point.y - canvasGesture.start.y))
    );
    renderCanvas();
  }
}

function endCanvasGesture(event) {
  if (!canvasGesture) return;
  const gesture = canvasGesture;
  canvasGesture = null;
  elements.canvasViewport.dataset.panning = "false";
  const board = activeBoard();
  if (gesture.kind === "pan") return;
  if (gesture.kind === "box") {
    const overlay = elements.canvasStage.querySelector(".canvas-box");
    const box = overlay
      ? {
          x: parseFloat(overlay.style.left),
          y: parseFloat(overlay.style.top),
          width: parseFloat(overlay.style.width),
          height: parseFloat(overlay.style.height),
        }
      : null;
    if (overlay) overlay.remove();
    if (!box || !board) return;
    const hit =
      box.width > 3 || box.height > 3
        ? board.nodes
            .filter(
              (node) =>
                node.layout.x >= box.x - 1 &&
                node.layout.y >= box.y - 1 &&
                node.layout.x + node.layout.width <= box.x + box.width + 1 &&
                node.layout.y + node.layout.height <= box.y + box.height + 1
            )
            .map((node) => node.id)
        : [];
    state.canvasSelection = event.shiftKey
      ? [...new Set([...state.canvasSelection, ...hit])]
      : hit;
    renderCanvas();
    return;
  }
  if (!board) return;
  if (gesture.kind === "move") {
    const moved = gesture.origins
      .map((origin) => {
        const node = board.nodes.find((item) => item.id === origin.id);
        if (!node) return null;
        return {
          id: origin.id,
          dx: Math.round((node.layout.x - origin.layout.x) * 1000) / 1000,
          dy: Math.round((node.layout.y - origin.layout.y) * 1000) / 1000,
        };
      })
      .filter((entry) => entry && (entry.dx !== 0 || entry.dy !== 0));
    if (moved.length === 0) return;
    queueCanvasCommand({
      kind: "node-move",
      boardId: board.id,
      nodeIds: moved.map((entry) => entry.id),
      dx: moved[0].dx,
      dy: moved[0].dy,
    });
    return;
  }
  if (gesture.kind === "resize") {
    const node = board.nodes.find((item) => item.id === gesture.nodeId);
    if (!node) return;
    if (
      node.layout.width === gesture.origin.width &&
      node.layout.height === gesture.origin.height
    ) {
      return;
    }
    queueCanvasCommand({
      kind: "node-resize",
      boardId: board.id,
      nodeId: node.id,
      layout: {
        x: node.layout.x,
        y: node.layout.y,
        width: node.layout.width,
        height: node.layout.height,
      },
    });
  }
}

// -- keyboard alternatives ----------------------------------------------

function moveSelectionBy(dx, dy) {
  const board = activeBoard();
  if (!board || state.canvasSelection.length === 0) return;
  queueCanvasCommand({
    kind: "node-move",
    boardId: board.id,
    nodeIds: [...state.canvasSelection],
    dx,
    dy,
  });
}

async function canvasUndoRedo(verb) {
  if (!state.canvas) return;
  if (state.canvasQueue.length > 0) await flushCanvasQueue();
  if (state.canvasQueue.length > 0) {
    announce("先处理未保存的编辑，再撤销。");
    return;
  }
  try {
    const payload = await api(canvasActionPath(verb), {
      method: "POST",
      body: {
        operation: mutation(
          newOperationId(),
          { action: verb, canvasId: state.canvas.canvasId },
          state.canvasCounter
        ),
      },
    });
    adoptCanvasPayload(payload);
    setCanvasSaveState("saved");
    announce(verb === "undo" ? "已撤销一步。" : "已重做一步。");
  } catch (error) {
    if (error.status === 409) {
      setCanvasSaveState("conflict");
    } else {
      showCanvasError(error, verb === "undo" ? "撤销" : "重做");
    }
  }
}

function canvasKeydown(event) {
  if (!state.canvas) return;
  const target = event.target;
  if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
  const step = event.shiftKey ? 10 : 1;
  const key = event.key;
  if (key === "ArrowLeft") {
    moveSelectionBy(-step, 0);
  } else if (key === "ArrowRight") {
    moveSelectionBy(step, 0);
  } else if (key === "ArrowUp") {
    moveSelectionBy(0, -step);
  } else if (key === "ArrowDown") {
    moveSelectionBy(0, step);
  } else if (key === "Delete" || key === "Backspace") {
    deleteSelection();
  } else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "d") {
    duplicateSelection();
  } else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "g") {
    groupSelection();
  } else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "a") {
    const board = activeBoard();
    state.canvasSelection = board ? board.nodes.map((node) => node.id) : [];
    renderCanvas();
  } else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "z") {
    canvasUndoRedo(event.shiftKey ? "redo" : "undo");
  } else if (key === "Escape") {
    state.canvasSelection = [];
    renderCanvas();
    return;
  } else if (key === "+" || key === "=") {
    setCanvasZoom(state.canvasView.scale * 1.1);
  } else if (key === "-") {
    setCanvasZoom(state.canvasView.scale / 1.1);
  } else {
    return;
  }
  event.preventDefault();
}

// -- selection operations -----------------------------------------------

function deleteSelection() {
  const board = activeBoard();
  if (!board || state.canvasSelection.length === 0) return;
  const nodeIds = [...state.canvasSelection];
  queueCanvasCommand({ kind: "node-delete", boardId: board.id, nodeIds });
  state.canvasSelection = [];
  renderCanvas();
}

function duplicateSelection() {
  const board = activeBoard();
  if (!board || state.canvasSelection.length === 0) return;
  queueCanvasCommand(
    { kind: "node-duplicate", boardId: board.id, nodeIds: [...state.canvasSelection] },
    { selectCreated: true }
  );
}

function groupSelection() {
  const board = activeBoard();
  if (!board || state.canvasSelection.length < 2) {
    announce("成组需要至少两个节点。");
    return;
  }
  queueCanvasCommand(
    { kind: "node-group", boardId: board.id, nodeIds: [...state.canvasSelection] },
    { selectCreated: true }
  );
}

function alignSelection(mode) {
  const board = activeBoard();
  if (!board || state.canvasSelection.length < 2) {
    announce("对齐需要至少两个节点。");
    return;
  }
  queueCanvasCommand({
    kind: "node-align",
    boardId: board.id,
    nodeIds: [...state.canvasSelection],
    mode,
  });
}

function layerSelection(action) {
  const board = activeBoard();
  const nodes = selectedNodes();
  if (!board || nodes.length !== 1) {
    announce("图层操作一次作用于一个节点。");
    return;
  }
  queueCanvasCommand({
    kind: "node-reorder",
    boardId: board.id,
    nodeId: nodes[0].id,
    action,
  });
}

// -- board and canvas lifecycle ------------------------------------------

async function loadCanvases() {
  const project = state.canvasProject;
  if (!project) return;
  try {
    const payload = await api(canvasPath(""));
    state.canvases = payload.canvases || [];
    elements.canvasSelect.textContent = "";
    for (const row of state.canvases) {
      const option = document.createElement("option");
      option.value = row.canvasId;
      option.textContent = `${row.name}（${row.boardCount} 画板）`;
      elements.canvasSelect.appendChild(option);
    }
    if (state.canvases.length === 0) {
      state.canvas = null;
      state.canvasDocument = null;
      setCanvasSaveState("idle", "还没有画布：先新建一个。");
      renderCanvas();
      return;
    }
    const wanted = state.canvas ? state.canvas.canvasId : state.canvases[0].canvasId;
    await loadCanvas(
      state.canvases.some((row) => row.canvasId === wanted)
        ? wanted
        : state.canvases[0].canvasId
    );
  } catch (error) {
    showCanvasError(error, "读取画布列表");
  }
}

async function loadCanvas(canvasId) {
  try {
    const payload = await api(canvasPath("/" + canvasId));
    state.canvas = payload.canvas;
    state.canvasCounter = payload.canvas.counter;
    state.canvasDocument = payload.document;
    state.canvasHistory = payload.history;
    state.canvasBoardId = (payload.document.boards || [])[0]?.id || null;
    state.canvasSelection = [];
    state.canvasQueue = [];
    clearCanvasTimers();
    elements.canvasError.hidden = true;
    elements.canvasSelect.value = canvasId;
    setCanvasSaveState("saved", "已保存（已载入服务端状态）");
    renderCanvas();
    fitCanvasView();
    renderContext(null);
    await loadSnapshots();
  } catch (error) {
    showCanvasError(error, "读取画布");
  }
}

async function loadProjectInstances() {
  const project = state.canvasProject;
  if (!project) return;
  try {
    const payload = await api(`/api/v1/projects/${project.projectId}/instances`);
    state.canvasInstances = new Map(
      (payload.instances || []).map((row) => [row.instanceId, row])
    );
  } catch (error) {
    state.canvasInstances = new Map();
    showCanvasError(error, "读取固定资产实例");
  }
}

async function openCanvas(project) {
  state.canvasProject = project;
  elements.canvasHeading.textContent = `画布 · ${project.name}`;
  elements.canvasScope.textContent =
    `项目：${project.name} · 目录：${project.canonicalPath}`;
  elements.canvasError.hidden = true;
  elements.canvasPanel.hidden = false;
  focusIntoPanel(elements.canvasHeading);
  await loadProjectInstances();
  await loadCanvases();
  announce("已打开画布。");
}

async function createCanvas(event) {
  event.preventDefault();
  const project = state.canvasProject;
  if (!project) return;
  const name = elements.canvasName.value.trim() || "新画布";
  const template = {
    name,
    boards: [
      {
        id: "b_" + Math.random().toString(16).slice(2, 14),
        name: "画板 1",
        width: 1200,
        height: 800,
        nodes: [
          {
            id: "n_" + Math.random().toString(16).slice(2, 14),
            type: "text",
            children: [],
            props: { text: "标题" },
            layout: { x: 48, y: 48, width: 240, height: 40, z: 0 },
          },
        ],
        flowEdges: [],
      },
    ],
  };
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/canvases`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), { action: "canvases", name }),
          name,
          document: template,
        },
      }
    );
    elements.canvasName.value = "";
    state.canvas = payload.result.canvas;
    state.canvasCounter = payload.result.canvas.counter;
    state.canvasDocument = payload.result.document;
    state.canvasHistory = payload.result.history;
    state.canvasBoardId = payload.result.document.boards[0].id;
    state.canvasSelection = [];
    state.canvasQueue = [];
    elements.canvasError.hidden = true;
    setCanvasSaveState("saved");
    await loadCanvases();
    announce("已新建画布。");
  } catch (error) {
    showCanvasError(error, "新建画布");
  }
}

async function addBoard() {
  if (!state.canvas) return;
  const existing = (state.canvasDocument.boards || []).length;
  queueCanvasCommand({
    kind: "board-add",
    boardId: "b_" + Math.random().toString(16).slice(2, 14),
    name: `画板 ${existing + 1}`,
    width: 1200,
    height: 800,
  });
  await flushCanvasQueue();
  const boards = state.canvasDocument.boards || [];
  state.canvasBoardId = boards.length ? boards[boards.length - 1].id : null;
  renderCanvas();
  fitCanvasView();
}

function resizeBoard() {
  const board = activeBoard();
  if (!board || !state.canvas) return;
  const width = Number(elements.boardWidth.value);
  const height = Number(elements.boardHeight.value);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    announce("画板尺寸必须是正数。");
    return;
  }
  queueCanvasCommand({ kind: "board-resize", boardId: board.id, width, height });
}

function canvasContentField(node) {
  const props = node.props || {};
  if (node.type === "text") return { label: "文本", field: "text", value: props.text || "" };
  if (node.type === "button") {
    return { label: "按钮文本", field: "label", value: props.label || "" };
  }
  if (node.type === "link") return { label: "链接文本", field: "label", value: props.label || "" };
  if (node.type === "image") {
    return { label: "图片来源", field: "source", value: props.source || "" };
  }
  if (node.type === "slot") return { label: "slot 名", field: "name", value: props.name || "" };
  return { label: "标签", field: "label", value: props.label || "" };
}

function applyNodeContent() {
  const nodes = selectedNodes();
  if (nodes.length !== 1) return;
  const node = nodes[0];
  const board = activeBoard();
  const content = canvasContentField(node);
  const value = elements.propContent.value;
  queueCanvasCommand({
    kind: "node-props",
    boardId: board.id,
    nodeId: node.id,
    props: { [content.field]: value },
  });
}

function applyNodeToken() {
  const nodes = selectedNodes();
  if (nodes.length !== 1) return;
  const board = activeBoard();
  queueCanvasCommand({
    kind: "node-props",
    boardId: board.id,
    nodeId: nodes[0].id,
    props: { tokenRef: elements.propToken.value.trim() },
  });
}

function applyNodeGeometry() {
  const nodes = selectedNodes();
  if (nodes.length !== 1) return;
  const node = nodes[0];
  const board = activeBoard();
  const x = Number(elements.propX.value);
  const y = Number(elements.propY.value);
  const width = Number(elements.propWidth.value);
  const height = Number(elements.propHeight.value);
  if (
    ![x, y, width, height].every((value) => Number.isFinite(value)) ||
    width <= 0 ||
    height <= 0
  ) {
    announce("节点几何必须是正数。");
    return;
  }
  if (x !== node.layout.x || y !== node.layout.y) {
    queueCanvasCommand({
      kind: "node-move",
      boardId: board.id,
      nodeIds: [node.id],
      dx: x - node.layout.x,
      dy: y - node.layout.y,
    });
  }
  if (width !== node.layout.width || height !== node.layout.height) {
    queueCanvasCommand({
      kind: "node-resize",
      boardId: board.id,
      nodeId: node.id,
      layout: { x, y, width, height },
    });
  }
}

function applyInstanceParams() {
  const nodes = selectedNodes();
  if (nodes.length !== 1 || nodes[0].type !== "instance") return;
  const board = activeBoard();
  let params;
  try {
    params = JSON.parse(elements.canvasInstanceParams.value || "{}");
  } catch (error) {
    showCanvasError({ message: error.message, code: "invalid-input" }, "解析实例参数");
    return;
  }
  queueCanvasCommand({
    kind: "instance-params",
    boardId: board.id,
    nodeId: nodes[0].id,
    params,
  });
}

async function upgradeInstance() {
  const nodes = selectedNodes();
  if (nodes.length !== 1 || nodes[0].type !== "instance") return;
  const project = state.canvasProject;
  const row = state.canvasInstances.get(nodes[0].props.instanceId);
  if (!row) return;
  try {
    // Upgrade stays a reuse-owner operation: the canvas only names the
    // instance whose fixed revision should move.
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${row.assetId}/upgrade`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "upgrade",
            assetId: row.assetId,
            instanceIds: [nodes[0].props.instanceId],
          }),
          instanceIds: [nodes[0].props.instanceId],
        },
      }
    );
    await loadProjectInstances();
    renderCanvas();
    announce(`实例已升级（${payload.result.updatedInstanceIds.length} 个）。`);
  } catch (error) {
    showCanvasError(error, "升级实例版本");
  }
}

async function forkCanvas() {
  if (!state.canvas) return;
  const name = window.prompt(
    "冲突草稿另存为新画布的名称",
    `${state.canvas.name} 分支`
  );
  if (name === null) return;
  try {
    const payload = await api(canvasActionPath("fork"), {
      method: "POST",
      body: {
        operation: mutation(newOperationId(), {
          action: "fork",
          canvasId: state.canvas.canvasId,
        }),
        name,
        document: state.canvasDocument,
      },
    });
    state.canvas = payload.result.canvas;
    state.canvasCounter = payload.result.canvas.counter;
    state.canvasDocument = payload.result.document;
    state.canvasHistory = payload.result.history;
    state.canvasBoardId = payload.result.document.boards[0].id;
    state.canvasQueue = [];
    elements.canvasError.hidden = true;
    setCanvasSaveState("saved");
    await loadCanvases();
    announce("已把本页草稿另存为新画布。");
  } catch (error) {
    showCanvasError(error, "另存分支");
  }
}

async function showCanvasSnapshot() {
  if (!state.canvas) return;
  try {
    const payload = await api(
      canvasPath(
        `/${state.canvas.canvasId}/snapshot?boardId=${encodeURIComponent(
          state.canvasBoardId
        )}`
      )
    );
    elements.canvasSnapshotFrame.setAttribute("sandbox", "");
    elements.canvasSnapshotFrame.setAttribute("src", payload.previewUrl);
    elements.canvasSnapshotFrame.hidden = false;
    elements.canvasSnapshotNote.textContent =
      `${payload.note} 画板：${payload.boardName} · hash ${String(
        payload.contentHash
      ).slice(0, 19)}…`;
    announce("已生成静态布局快照。");
  } catch (error) {
    showCanvasError(error, "生成快照");
  }
}

async function placeAssetOnCanvas(asset, point) {
  const project = state.canvasProject || state.assetsProject;
  if (!project || !asset) return;
  if (elements.canvasPanel.hidden) await openCanvas(project);
  const board = activeBoard();
  if (!board) {
    announce("先新建或载入一个画板。");
    return;
  }
  try {
    const created = await api(
      `/api/v1/projects/${project.projectId}/actions/instances`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "instances",
            assetId: asset.assetId,
          }),
          assetId: asset.assetId,
        },
      }
    );
    const instance = created.result;
    state.canvasInstances.set(instance.instanceId, instance);
    const node = {
      id: "n_" + Math.random().toString(16).slice(2, 14),
      type: "instance",
      children: [],
      props: { instanceId: instance.instanceId, params: {} },
      layout: {
        x: Math.round(point && point.x !== undefined ? point.x : 40),
        y: Math.round(point && point.y !== undefined ? point.y : 40),
        width: 200,
        height: 80,
        z: board.nodes.length,
      },
    };
    queueCanvasCommand(
      { kind: "node-add", boardId: board.id, node },
      { selectCreated: true }
    );
  } catch (error) {
    showCanvasError(error, "放入画布");
  }
}

// -- wiring --------------------------------------------------------------

elements.canvasCreateForm.addEventListener("submit", createCanvas);
elements.canvasSelect.addEventListener("change", () =>
  loadCanvas(elements.canvasSelect.value)
);
elements.canvasReload.addEventListener("click", () => loadCanvases());
elements.canvasBoardSelect.addEventListener("change", () => {
  state.canvasBoardId = elements.canvasBoardSelect.value;
  state.canvasSelection = [];
  renderCanvas();
});
elements.canvasBoardAdd.addEventListener("click", addBoard);
elements.canvasZoomIn.addEventListener("click", () =>
  setCanvasZoom(state.canvasView.scale * 1.2)
);
elements.canvasZoomOut.addEventListener("click", () =>
  setCanvasZoom(state.canvasView.scale / 1.2)
);
elements.canvasFit.addEventListener("click", fitCanvasView);
elements.canvasUndo.addEventListener("click", () => canvasUndoRedo("undo"));
elements.canvasRedo.addEventListener("click", () => canvasUndoRedo("redo"));
elements.canvasGroup.addEventListener("click", groupSelection);
elements.canvasDuplicate.addEventListener("click", duplicateSelection);
elements.canvasDelete.addEventListener("click", deleteSelection);
elements.canvasSnapshot.addEventListener("click", showCanvasSnapshot);
elements.canvasRetry.addEventListener("click", () => flushCanvasQueue());
elements.canvasFork.addEventListener("click", forkCanvas);
elements.boardResize.addEventListener("click", resizeBoard);
elements.canvasInstanceApply.addEventListener("click", applyInstanceParams);
elements.canvasInstanceUpgrade.addEventListener("click", upgradeInstance);
elements.propX.addEventListener("change", applyNodeGeometry);
elements.propY.addEventListener("change", applyNodeGeometry);
elements.propWidth.addEventListener("change", applyNodeGeometry);
elements.propHeight.addEventListener("change", applyNodeGeometry);
elements.propContentApply.addEventListener("click", applyNodeContent);
elements.propTokenApply.addEventListener("click", applyNodeToken);
for (const button of document.querySelectorAll(".canvas-align")) {
  button.addEventListener("click", () => alignSelection(button.dataset.align));
}
for (const button of document.querySelectorAll(".canvas-layer")) {
  button.addEventListener("click", () => layerSelection(button.dataset.action));
}
elements.canvasViewport.addEventListener("pointerdown", beginCanvasGesture);
elements.canvasViewport.addEventListener("pointermove", updateCanvasGesture);
elements.canvasViewport.addEventListener("pointerup", endCanvasGesture);
elements.canvasViewport.addEventListener("pointercancel", endCanvasGesture);
elements.canvasPanel.addEventListener("keydown", canvasKeydown);
elements.canvasViewport.addEventListener("wheel", (event) => {
  if (!event.ctrlKey) return;
  event.preventDefault();
  setCanvasZoom(state.canvasView.scale * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
});
elements.canvasClose.addEventListener("click", async () => {
  if (canvasHasUnsavedEdits()) {
    const leave = window.confirm("画布还有未确认的编辑，确定关闭面板？");
    if (!leave) return;
  }
  await flushCanvasQueue();
  elements.canvasPanel.hidden = true;
  restorePanelTrigger();
  elements.canvasSnapshotFrame.hidden = true;
  elements.canvasSnapshotFrame.removeAttribute("src");
  state.canvasProject = null;
  announce("已关闭画布。");
});
elements.assetIntoCanvas.addEventListener("click", () =>
  placeAssetOnCanvas(state.selectedAsset)
);

// Dropping an asset on the board creates the fixed-revision instance and
// adds the node as one gesture.
let assetDrag = null;
elements.assetItemsList.addEventListener("pointerdown", (event) => {
  const item = event.target.closest(".asset-item");
  if (!item) return;
  assetDrag = { assetId: item.dataset.assetId };
});
window.addEventListener("pointerup", async (event) => {
  if (!assetDrag) return;
  const drag = assetDrag;
  assetDrag = null;
  const viewport = elements.canvasViewport;
  if (!viewport || elements.canvasPanel.hidden) return;
  const box = viewport.getBoundingClientRect();
  if (
    event.clientX < box.left ||
    event.clientX > box.right ||
    event.clientY < box.top ||
    event.clientY > box.bottom
  ) {
    return;
  }
  const stage = elements.canvasStage.getBoundingClientRect();
  const point = {
    x: (event.clientX - stage.left) / state.canvasView.scale - 100,
    y: (event.clientY - stage.top) / state.canvasView.scale - 40,
  };
  const asset =
    (state.assets || []).find((row) => row.assetId === drag.assetId) ||
    state.selectedAsset;
  await placeAssetOnCanvas(asset, point);
});

// -- orchestration: flows, schemes, snapshots, context (WB-08) ----------

function canvasOrchestrationPath(suffix) {
  const project = state.canvasProject;
  return `/api/v1/projects/${project.projectId}/canvases/${state.canvas.canvasId}${suffix}`;
}

function showOrchError(element, error, action) {
  element.hidden = false;
  element.textContent = describeFailure(error, action);
}

function flowEndpointOptions(select, board) {
  const previous = select.value;
  select.textContent = "";
  for (const node of board.nodes) {
    const option = document.createElement("option");
    option.value = node.id;
    option.textContent = `${canvasNodeLabel(node)} (${node.id})`;
    select.appendChild(option);
  }
  for (const other of state.canvasDocument.boards) {
    if (other.id === board.id) continue;
    const option = document.createElement("option");
    option.value = other.id;
    option.textContent = `画板：${other.name}`;
    select.appendChild(option);
  }
  if (previous) select.value = previous;
}

function renderFlows() {
  const board = activeBoard();
  if (!board) return;
  flowEndpointOptions(elements.flowFrom, board);
  flowEndpointOptions(elements.flowTo, board);
  elements.flowList.textContent = "";
  if (board.flowEdges.length === 0) {
    const item = document.createElement("li");
    item.textContent = "当前画板还没有流程边。";
    elements.flowList.appendChild(item);
    return;
  }
  for (const edge of board.flowEdges) {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent =
      `${edge.from} → ${edge.to} · ${edge.kind}` +
      (edge.label ? ` · ${edge.label}` : "");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary";
    remove.textContent = "删除";
    remove.dataset.edgeId = edge.id;
    remove.addEventListener("click", () => deleteFlowEdge(edge.id));
    item.appendChild(text);
    item.appendChild(remove);
    elements.flowList.appendChild(item);
  }
}

function addFlowEdge() {
  const board = activeBoard();
  if (!board || !state.canvas) return;
  if (!elements.flowFrom.value || !elements.flowTo.value) {
    announce("流程边需要起点与终点。");
    return;
  }
  queueCanvasCommand({
    kind: "flow-edge-add",
    boardId: board.id,
    edge: {
      id: `f_${Math.random().toString(16).slice(2, 14)}`,
      from: elements.flowFrom.value,
      to: elements.flowTo.value,
      kind: elements.flowKind.value,
      label: elements.flowLabel.value.trim(),
    },
  });
  elements.flowLabel.value = "";
}

function deleteFlowEdge(edgeId) {
  const board = activeBoard();
  if (!board || !state.canvas) return;
  queueCanvasCommand({ kind: "flow-edge-delete", boardId: board.id, edgeId });
}

function renderScheme() {
  const board = activeBoard();
  if (!board) return;
  const scheme = board.scheme;
  elements.schemeWidth.value = scheme ? scheme.viewport.width : board.width;
  elements.schemeHeight.value = scheme ? scheme.viewport.height : board.height;
  elements.schemeDevice.value = scheme ? scheme.viewport.device || "" : "";
  elements.schemeRules.value = scheme ? (scheme.rules || []).join("\n") : "";
  elements.schemeRegions.value = scheme
    ? (scheme.replaceableRegions || []).join(", ")
    : "";
  elements.schemeAcceptance.value = scheme ? scheme.acceptance || "" : "";
  elements.schemeNote.textContent = scheme
    ? scheme.derivedFrom && scheme.derivedFrom.boardId
      ? `派生自画板 ${scheme.derivedFrom.boardId}${
          scheme.derivedFrom.snapshotId ? `（基线快照 ${scheme.derivedFrom.snapshotId.slice(0, 8)}）` : ""
        }；约束只描述方案，不授予批准。`
      : "已声明方案约束。"
    : "当前画板还没有方案约束。";
}

function saveScheme() {
  const board = activeBoard();
  if (!board || !state.canvas) return;
  const rules = elements.schemeRules.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const regions = elements.schemeRegions.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  queueCanvasCommand({
    kind: "board-scheme",
    boardId: board.id,
    scheme: {
      viewport: {
        width: Number(elements.schemeWidth.value),
        height: Number(elements.schemeHeight.value),
        device: elements.schemeDevice.value.trim(),
      },
      rules,
      replaceableRegions: regions,
      acceptance: elements.schemeAcceptance.value.trim(),
    },
  });
}

async function deriveScheme() {
  const board = activeBoard();
  if (!board || !state.canvas) return;
  const name = window.prompt("派生方案名称", `${board.name} 方案 B`);
  if (name === null) return;
  queueCanvasCommand({
    kind: "scheme-derive",
    boardId: board.id,
    newBoardId: `b_${Math.random().toString(16).slice(2, 14)}`,
    name,
  });
  await flushCanvasQueue();
  const boards = state.canvasDocument.boards;
  state.canvasBoardId = boards[boards.length - 1].id;
  renderCanvas();
}

// -- fixed snapshots and comparison -------------------------------------

async function loadSnapshots() {
  if (!state.canvas) return;
  try {
    const payload = await api(canvasOrchestrationPath("/snapshots"));
    state.snapshots = payload.snapshots || [];
    elements.snapshotList.textContent = "";
    if (state.snapshots.length === 0) {
      const item = document.createElement("li");
      item.textContent = "还没有固定快照。";
      elements.snapshotList.appendChild(item);
    }
    for (const row of state.snapshots) {
      const item = document.createElement("li");
      item.textContent =
        `${row.boardName} · counter ${row.counter} · ${row.nodeCount} 节点 · ` +
        `${String(row.contentHash).slice(0, 19)}…` +
        (row.note ? ` · ${row.note}` : "");
      elements.snapshotList.appendChild(item);
    }
    for (const select of [elements.compareLeft, elements.compareRight]) {
      const previous = select.value;
      select.textContent = "";
      for (const row of state.snapshots) {
        const option = document.createElement("option");
        option.value = row.snapshotId;
        option.textContent = `${row.boardName} · ${String(row.contentHash).slice(0, 12)}…`;
        select.appendChild(option);
      }
      if (previous && state.snapshots.some((row) => row.snapshotId === previous)) {
        select.value = previous;
      }
    }
    if (state.snapshots.length >= 2 && elements.compareRight.value === elements.compareLeft.value) {
      elements.compareRight.value = state.snapshots[0].snapshotId;
    }
  } catch (error) {
    showOrchError(elements.canvasError, error, "读取固定快照");
  }
}

async function createSnapshot() {
  if (!state.canvas) return;
  try {
    const payload = await api(
      `/api/v1/projects/${state.canvasProject.projectId}/actions/canvases/` +
        `${state.canvas.canvasId}/snapshots`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "snapshots",
            canvasId: state.canvas.canvasId,
          }),
          boardId: state.canvasBoardId,
        },
      }
    );
    elements.canvasError.hidden = true;
    await loadSnapshots();
    announce(`已固定快照（counter ${payload.result.counter}）。`);
  } catch (error) {
    showOrchError(elements.canvasError, error, "固定快照");
  }
}

async function runComparison() {
  if (!state.canvas) return;
  const left = elements.compareLeft.value;
  const right = elements.compareRight.value;
  if (!left || !right) {
    announce("先固定两份快照再比较。");
    return;
  }
  try {
    const payload = await api(
      `/api/v1/projects/${state.canvasProject.projectId}/actions/canvases/` +
        `${state.canvas.canvasId}/compare`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "compare",
            canvasId: state.canvas.canvasId,
          }),
          left,
          right,
        },
      }
    );
    const result = payload.result;
    elements.compareGrid.hidden = false;
    elements.compareLeftCaption.textContent =
      `左：${result.left.boardName} · counter ${result.left.counter} · ${result.left.nodeCount} 节点`;
    elements.compareRightCaption.textContent =
      `右：${result.right.boardName} · counter ${result.right.counter} · ${result.right.nodeCount} 节点`;
    elements.compareLeftFrame.setAttribute("src", result.left.previewUrl);
    elements.compareRightFrame.setAttribute("src", result.right.previewUrl);
    const counts = result.differences.nodeTypes
      .map((row) => `${row.type} ${row.left}→${row.right}`)
      .join("、");
    elements.compareNote.textContent =
      `${result.note}节点数 ${result.differences.nodeCount.left}→` +
      `${result.differences.nodeCount.right}；类型差异：${counts || "无"}；` +
      `${result.differences.sameContent ? "两份快照内容相同。" : "两份快照内容不同。"}`;
    announce("已并排比较两份固定快照。");
  } catch (error) {
    showOrchError(elements.canvasError, error, "比较快照");
  }
}

// -- context selection ---------------------------------------------------

function renderContext(selection) {
  state.context = selection;
  if (!selection) {
    elements.contextState.textContent = "还没有上下文选择。";
    elements.contextContent.textContent = "";
    elements.contextExclusions.textContent = "";
    elements.contextStale.hidden = true;
    return;
  }
  elements.contextState.textContent =
    `选择 ${selection.selectionId} · ${selection.state === "confirmed" ? "已确认" : "草稿"} · ` +
    `digest ${String(selection.digest).slice(0, 19)}…` +
    (selection.confirmed && selection.state === "confirmed"
      ? ` · 确认于 ${selection.confirmed.at}`
      : "");
  elements.contextStale.hidden = !selection.staleConfirmation;
  if (!elements.workPanel.hidden) renderWorkContextNote();
  elements.contextContent.textContent = "";
  const rows = [
    `节点 ${selection.totals.nodeCount} 个（${selection.totals.nodeBytes} 字节）`,
    `资产修订 ${selection.totals.revisionCount} 个（${selection.totals.revisionBytes} 字节）`,
    `文件 ${selection.totals.fileCount} 个（${selection.totals.fileBytes} 字节）`,
    `合计 ${selection.totals.bytes} 字节`,
    ...selection.nodes.map((node) => `节点：${node.type} ${node.nodeId}`),
    ...selection.revisions.map(
      (row) => `修订：${row.assetName} 第 ${row.revisionNumber} 次 · ${row.reason}`
    ),
    ...selection.files.map((row) => `文件：${row.path} · ${row.size} 字节`),
  ];
  for (const text of rows) {
    const item = document.createElement("li");
    item.textContent = text;
    elements.contextContent.appendChild(item);
  }
  elements.contextExclusions.textContent = "";
  for (const row of selection.exclusions) {
    const item = document.createElement("li");
    item.textContent = `排除：${row.kind}（${row.count}）· ${row.reason}`;
    elements.contextExclusions.appendChild(item);
  }
}

async function buildContext() {
  if (!state.canvas) return;
  const board = activeBoard();
  const files = elements.contextFiles.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    const payload = await api(
      `/api/v1/projects/${state.canvasProject.projectId}/actions/canvases/` +
        `${state.canvas.canvasId}/contexts`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "contexts",
            canvasId: state.canvas.canvasId,
          }),
          selectionId: state.context ? state.context.selectionId : undefined,
          boardId: board.id,
          nodeIds: [...state.canvasSelection],
          filePaths: files,
        },
      }
    );
    elements.contextError.hidden = true;
    renderContext(payload.result);
    announce("已更新上下文选择。");
  } catch (error) {
    showOrchError(elements.contextError, error, "建立上下文");
  }
}

async function confirmContext() {
  if (!state.canvas || !state.context) {
    announce("先建立一个上下文选择。");
    return;
  }
  try {
    const payload = await api(
      `/api/v1/projects/${state.canvasProject.projectId}/actions/canvases/` +
        `${state.canvas.canvasId}/confirm`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "confirm",
            canvasId: state.canvas.canvasId,
          }),
          selectionId: state.context.selectionId,
          digest: state.context.digest,
        },
      }
    );
    elements.contextError.hidden = true;
    renderContext(payload.result);
    announce("已确认发送范围。");
  } catch (error) {
    showOrchError(elements.contextError, error, "确认发送范围");
  }
}

elements.flowAdd.addEventListener("click", addFlowEdge);
elements.schemeSave.addEventListener("click", saveScheme);
elements.schemeDerive.addEventListener("click", deriveScheme);
elements.snapshotCreate.addEventListener("click", createSnapshot);
elements.compareRun.addEventListener("click", runComparison);
elements.contextBuild.addEventListener("click", buildContext);
elements.contextConfirm.addEventListener("click", confirmContext);

// -- Agent work requests: consent, leases, results (WB-10) --------------

const WORK_STATE_LABELS = {
  "awaiting-consent": "等待确认发送范围",
  "waiting-for-agent": "等待 Agent 接手",
  running: "执行中（服务端租约）",
  "proposal-ready": "已收到结果提案",
  applied: "提案已应用（未验证）",
  failed: "Agent 报告失败",
  interrupted: "中断（租约过期或服务重启）",
  "cancel-requested": "已请求取消（等待宿主确认）",
  cancelled: "已取消（宿主确认）",
  rejected: "已拒绝结果",
};

function workStateLabel(state) {
  return WORK_STATE_LABELS[state] || state;
}

function workPath(suffix) {
  const project = state.workProject;
  return `/api/v1/projects/${project.projectId}/requests${suffix}`;
}

function showWorkError(error, action) {
  elements.workError.hidden = false;
  elements.workError.textContent = describeFailure(error, action);
}

function selectedWorkRequest() {
  return (state.workRequests || []).find(
    (row) => row.requestId === state.workSelectedId
  );
}

async function openWork(project) {
  state.workProject = project;
  elements.workHeading.textContent = `Agent 任务 · ${project.name}`;
  elements.workScope.textContent =
    `项目：${project.name} · 目录：${project.canonicalPath}`;
  elements.workError.hidden = true;
  elements.workPanel.hidden = false;
  focusIntoPanel(elements.workHeading);
  renderWorkContextNote();
  await loadWorkRequests();
  announce("已打开 Agent 任务。");
}

function renderWorkContextNote() {
  const context = state.context;
  if (!context) {
    elements.workContextNote.textContent =
      "还没有上下文选择：先在画布面板用当前选择建立并确认上下文，任务才有发送范围。";
    return;
  }
  elements.workContextNote.textContent =
    `当前上下文 ${context.selectionId} · ${context.state === "confirmed" ? "已确认" : "未确认"}` +
    ` · 节点 ${context.totals.nodeCount} · 修订 ${context.totals.revisionCount}` +
    ` · 文件 ${context.totals.fileCount} · 合计 ${context.totals.bytes} 字节`;
}

async function loadWorkRequests() {
  const project = state.workProject;
  if (!project) return;
  try {
    const payload = await api(workPath(""));
    state.workRequests = payload.requests || [];
    elements.workError.hidden = true;
    renderWorkList();
    if (state.workSelectedId) {
      const still = selectedWorkRequest();
      if (still) {
        await selectWorkRequest(still.requestId);
      } else {
        state.workSelectedId = null;
        renderWorkDetail(null);
      }
    }
  } catch (error) {
    showWorkError(error, "读取任务");
  }
}

function renderWorkList() {
  elements.workList.textContent = "";
  if ((state.workRequests || []).length === 0) {
    const item = document.createElement("li");
    item.textContent = "该项目还没有任务请求。";
    elements.workList.appendChild(item);
    return;
  }
  for (const row of state.workRequests) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.dataset.requestId = row.requestId;
    button.textContent = `${row.title} · ${workStateLabel(row.state)} · ${row.targetStack}`;
    button.addEventListener("click", () => selectWorkRequest(row.requestId));
    item.appendChild(button);
    elements.workList.appendChild(item);
  }
}

function renderWorkDetail(request) {
  elements.workDetail.hidden = request === null;
  if (!request) return;
  elements.workDetailHeading.textContent = request.title;
  elements.workDetailState.textContent =
    workStateLabel(request.state) + (request.applied ? " · 已应用" : "") +
    (request.verified ? " · 已验证" : " · 未验证");
  elements.workDetailCapability.textContent = request.capabilityId
    ? `${request.capabilityId}（凭证本体保存在本机受保护记录中，界面不显示）`
    : "尚未生成";
  elements.workDetailContext.textContent =
    `${request.contextSelectionId} · digest ${String(request.contextDigest).slice(0, 19)}…` +
    (request.contextStillConfirmed ? " · 仍为已确认" : " · 已失效，需重新确认");
  elements.workDetailExpiry.textContent = request.expiresAt
    ? formatLocalTime(request.expiresAt)
    : "不过期";
  elements.workDetailPlan.textContent =
    `复用 ${request.plan.reuse.length} · 适配 ${request.plan.adapt.length} · 新增 ${request.plan.new.length}` +
    ` · 允许动作：${request.allowedActions.join("、")}`;
  elements.workHandoff.textContent = request.handoffCommand || "（尚未确认发送范围）";
  elements.workHandoffNote.textContent = request.handoffCommand
    ? "接手命令只包含项目路径与请求 ID；凭证由 slash 入口从本机受保护记录读取，不经过命令行或网页。"
    : "确认发送范围后才会生成接手命令。";

  elements.workAttempt.textContent = request.attempt
    ? `最近一次 attempt #${request.attempt.sequence} · ${request.attempt.state} · ` +
      `租约到期 ${formatLocalTime(request.attempt.leaseExpiresAt)} · ` +
      `进度 ${JSON.stringify(request.attempt.progress || {})}`
    : "还没有 Agent 接手：状态保持 waiting-for-agent，界面不推测进度。";
  elements.workAttempts.textContent = "";
  for (const attempt of request.attempts || []) {
    const item = document.createElement("li");
    item.textContent =
      `attempt #${attempt.sequence} · ${attempt.state} · 结果 ${attempt.resultDigest ? String(attempt.resultDigest).slice(0, 19) + "…" : "无"}` +
      (attempt.proposalId ? ` · 提案 ${attempt.proposalId}` : "");
    elements.workAttempts.appendChild(item);
  }

  elements.workResult.textContent = request.attempt && request.attempt.result
    ? `${request.attempt.result.summary} · 目标栈 ${request.attempt.result.targetStack} · ` +
      `依赖变更 ${request.attempt.result.dependencies.length} · ` +
      `入口 ${JSON.stringify(request.attempt.result.entrypoints)}`
    : "还没有结果。";
  elements.workResultList.textContent = "";
  const result = request.attempt ? request.attempt.result : null;
  if (result) {
    const rows = [
      `源码变更 ${result.changes.length} 个文件（经变更提案写回，需维护者批准）`,
      ...result.changes.map((change) => `变更：${change.operation} ${change.path}`),
      ...result.dependencies.map(
        (dependency) => `依赖：${dependency.name || dependency.path || JSON.stringify(dependency)}`
      ),
      ...result.artifacts.map((artifact) => `产物：${artifact.path} · ${artifact.hash || "无 hash"}`),
      result.runReceipt
        ? `运行回执：${result.runReceipt.command || ""}（退出码 ${result.runReceipt.exitCode}）`
        : "运行回执：无",
    ];
    for (const text of rows) {
      const item = document.createElement("li");
      item.textContent = text;
      elements.workResultList.appendChild(item);
    }
  }
}

async function selectWorkRequest(requestId) {
  state.workSelectedId = requestId;
  try {
    const payload = await api(workPath(`/${requestId}`));
    elements.workError.hidden = true;
    renderWorkDetail(payload.request);
  } catch (error) {
    showWorkError(error, "读取任务详情");
  }
}

function linesOf(element) {
  return element.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

async function createWorkRequest() {
  const project = state.workProject;
  const context = state.context;
  if (!project) return;
  if (!context) {
    showWorkError(
      { code: "missing-dependency", message: "还没有上下文选择。" },
      "建立任务"
    );
    return;
  }
  const title = elements.workTitle.value.trim();
  const goal = elements.workGoal.value.trim();
  if (!title || !goal) {
    announce("任务需要标题与目标。");
    return;
  }
  const actions = [...document.querySelectorAll(".work-action:checked")].map(
    (input) => input.value
  );
  const required = elements.workRequired.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/requests`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), { action: "requests", title }),
          title,
          goal,
          targetStack: elements.workStack.value,
          contextSelectionId: context.selectionId,
          expiresInSeconds: Number(elements.workExpiry.value) || 86400,
          plan: {
            reuse: linesOf(elements.workReuse),
            adapt: linesOf(elements.workAdapt),
            new: linesOf(elements.workNew),
          },
          allowedActions: actions,
          resultSchema: { required },
        },
      }
    );
    elements.workError.hidden = true;
    state.workSelectedId = payload.result.requestId;
    await loadWorkRequests();
    announce("已建立任务请求，等待确认发送范围。");
  } catch (error) {
    showWorkError(error, "建立任务");
  }
}

async function workVerb(verb, body) {
  const project = state.workProject;
  const request = selectedWorkRequest();
  if (!project || !request) return;
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/requests/` +
        `${request.requestId}/${verb}`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: verb,
            requestId: request.requestId,
          }),
          ...(body || {}),
        },
      }
    );
    elements.workError.hidden = true;
    await loadWorkRequests();
    announce(`已提交 ${verb}。`);
    return payload;
  } catch (error) {
    showWorkError(error, `提交 ${verb}`);
    return null;
  }
}

function consentWork() {
  const request = selectedWorkRequest();
  if (!request) return;
  return workVerb("consent", { digest: request.contextDigest });
}

function cancelWork() {
  return workVerb("cancel");
}

function confirmCancelled() {
  return workVerb("confirm-cancelled");
}

function retryWork() {
  return workVerb("retry");
}

function rejectWork() {
  return workVerb("reject");
}

async function copyHandoff() {
  const request = selectedWorkRequest();
  if (!request || !request.handoffCommand) return;
  try {
    await navigator.clipboard.writeText(request.handoffCommand);
    announce("已复制接手命令。");
  } catch (error) {
    // Clipboard access can be denied; the command stays visible on screen.
    elements.workHandoff.focus();
    announce("无法访问剪贴板，请手动复制屏幕上的命令。");
  }
}

elements.workCreate.addEventListener("click", createWorkRequest);
elements.workReload.addEventListener("click", () => loadWorkRequests());
elements.workConsent.addEventListener("click", consentWork);
elements.workCancel.addEventListener("click", cancelWork);
elements.workConfirmCancel.addEventListener("click", confirmCancelled);
elements.workRetry.addEventListener("click", retryWork);
elements.workReject.addEventListener("click", rejectWork);
elements.workCopyHandoff.addEventListener("click", copyHandoff);
elements.workClose.addEventListener("click", () => {
  elements.workPanel.hidden = true;
  restorePanelTrigger();
  state.workProject = null;
  state.workSelectedId = null;
  announce("已关闭 Agent 任务面板。");
});

// -- original owner facts, confirmations, backflow (WB-11) --------------

function ownerPath(suffix) {
  const project = state.ownerProject;
  return `/api/v1/projects/${project.projectId}${suffix}`;
}

function showOwnerError(error, action) {
  elements.ownerError.hidden = false;
  elements.ownerError.textContent = describeFailure(error, action);
}

async function openOwner(project) {
  state.ownerProject = project;
  elements.ownerHeading.textContent = `原 owner 验证 · ${project.name}`;
  elements.ownerScope.textContent =
    `项目：${project.name} · 目录：${project.canonicalPath}`;
  elements.ownerError.hidden = true;
  elements.ownerPanel.hidden = false;
  focusIntoPanel(elements.ownerHeading);
  await loadOwnerRuns();
  await loadOwnerConfirmations();
  announce("已打开原 owner 验证。");
}

async function loadOwnerRuns() {
  const project = state.ownerProject;
  if (!project) return;
  try {
    const payload = await api(ownerPath("/runs"));
    state.ownerRuns = payload.runs || [];
    elements.ownerRun.textContent = "";
    for (const row of state.ownerRuns) {
      const option = document.createElement("option");
      option.value = row.runId;
      option.textContent =
        `${row.runId}` +
        (row.state === "unknown"
          ? `（无法读取：${row.reason || ""}）`
          : ` · ${row.owner} · 判据 ${row.criteria}`);
      option.disabled = row.state === "unknown";
      elements.ownerRun.appendChild(option);
    }
    elements.ownerError.hidden = true;
    const readable = state.ownerRuns.find((row) => row.state !== "unknown");
    if (readable) {
      elements.ownerRun.value = readable.runId;
      await loadOwnerRun(readable.runId);
    } else {
      elements.ownerRunNote.textContent =
        state.ownerRuns.length === 0
          ? "项目内还没有 owner 投影（.design-playbook/runs/<run>/projection.json）。"
          : "投影不可读：请检查 owner 是否发布了有效投影。";
      elements.ownerCriteria.textContent = "";
      elements.ownerEvidence.textContent = "";
      elements.ownerFindings.textContent = "";
    }
  } catch (error) {
    showOwnerError(error, "读取 owner 运行");
  }
}

async function loadOwnerRun(runId) {
  const project = state.ownerProject;
  if (!project) return;
  try {
    const payload = await api(ownerPath(`/runs/${runId}`));
    elements.ownerError.hidden = true;
    renderOwnerRun(payload);
  } catch (error) {
    elements.ownerCriteria.textContent = "";
    elements.ownerEvidence.textContent = "";
    elements.ownerFindings.textContent = "";
    showOwnerError(error, "读取 owner 投影");
  }
}

function ownerConfirmButton(runId, row, sourceHash) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  button.textContent = row.confirmation ? "已确认" : "确认（owner-verified）";
  button.disabled = Boolean(row.confirmation) || !sourceHash;
  button.addEventListener("click", () =>
    confirmOwnerObject(runId, row.objectType, row.objectId, sourceHash)
  );
  return button;
}

function renderOwnerRun(run) {
  state.ownerRun = run;
  elements.ownerRunNote.textContent =
    `${run.owner} · ${run.runner || ""} · 生成于 ${run.generatedAt || "?"} · ` +
    `判据 ${run.criteria.length} · 证据 ${run.evidence.length} · 问题 ${run.findings.length}` +
    `（判据来源：${run.verdictSource}，工作台不重新裁决）`;

  elements.ownerCriteria.textContent = "";
  for (const row of run.criteria) {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent =
      `${row.objectId} · ${row.verdict}` +
      (row.role ? ` · 角色 ${row.role}` : "") +
      (row.confirmation ? ` · 已确认（${row.confirmation.role}）` : "");
    item.appendChild(text);
    item.appendChild(ownerConfirmButton(run.runId, row, row.sourceHash));
    elements.ownerCriteria.appendChild(item);
  }

  elements.ownerEvidence.textContent = "";
  for (const row of run.evidence) {
    const item = document.createElement("li");
    item.textContent =
      `${row.objectId} · ${row.kind}` +
      (row.hash ? ` · ${String(row.hash).slice(0, 19)}…` : "") +
      (row.criterionId ? ` · 判据 ${row.criterionId}` : "");
    elements.ownerEvidence.appendChild(item);
  }

  elements.ownerFindings.textContent = "";
  for (const row of run.findings) {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent =
      `${row.objectId} · ${row.severity} · ${row.summary} · 指回 ${row.pointBack.kind}` +
      (row.pointBack.path ? ` ${row.pointBack.path}` : "") +
      (row.pointBack.repairOwner ? ` · 修复 owner ${row.pointBack.repairOwner}` : "");
    item.appendChild(text);
    const backflow = document.createElement("button");
    backflow.type = "button";
    backflow.className = "secondary";
    backflow.textContent = "回流为候选";
    backflow.addEventListener(
      "click",
      () => backflowOwnerObject(run.runId, "finding", row.objectId)
    );
    item.appendChild(backflow);
    elements.ownerFindings.appendChild(item);
  }
}

async function confirmOwnerObject(runId, objectType, objectId, sourceHash) {
  const project = state.ownerProject;
  if (!project || !sourceHash) return;
  const note = window.prompt("确认说明（可选）", "");
  if (note === null) return;
  try {
    await api(`/api/v1/projects/${project.projectId}/actions/confirmations`, {
      method: "POST",
      body: {
        operation: mutation(newOperationId(), {
          action: "confirmations",
          runId,
          objectId,
        }),
        runId,
        objectType,
        objectId,
        sourceHash,
        role: "owner-verified",
        note,
      },
    });
    elements.ownerError.hidden = true;
    await loadOwnerRun(runId);
    await loadOwnerConfirmations();
    announce("已记录人工确认（绑定当前对象 hash）。");
  } catch (error) {
    showOwnerError(error, "记录确认");
  }
}

async function backflowOwnerObject(runId, objectType, objectId) {
  const project = state.ownerProject;
  if (!project) return;
  const name = window.prompt("回流候选名称", `${objectId} 候选`);
  if (name === null) return;
  try {
    const payload = await api(
      `/api/v1/projects/${project.projectId}/actions/backflow`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: "backflow",
            runId,
            objectId,
          }),
          runId,
          objectType,
          objectId,
          name,
        },
      }
    );
    elements.ownerError.hidden = true;
    announce(
      `已创建回流候选 ${payload.result.assetId}（草稿，需补全后发布；原 run 判据不变）。`
    );
  } catch (error) {
    showOwnerError(error, "回流候选");
  }
}

async function loadOwnerConfirmations() {
  const project = state.ownerProject;
  if (!project) return;
  try {
    const payload = await api(ownerPath("/confirmations"));
    elements.ownerConfirmations.textContent = "";
    if ((payload.confirmations || []).length === 0) {
      const item = document.createElement("li");
      item.textContent = "还没有人工确认。";
      elements.ownerConfirmations.appendChild(item);
      return;
    }
    for (const row of payload.confirmations) {
      const item = document.createElement("li");
      item.textContent =
        `${row.runId} · ${row.objectType} ${row.objectId} · ${row.role} · ` +
        `${String(row.sourceHash).slice(0, 19)}… · ${row.createdAt}`;
      elements.ownerConfirmations.appendChild(item);
    }
  } catch (error) {
    showOwnerError(error, "读取确认记录");
  }
}

elements.ownerRun.addEventListener("change", () => loadOwnerRun(elements.ownerRun.value));
elements.ownerReload.addEventListener("click", () => loadOwnerRuns());
elements.ownerClose.addEventListener("click", () => {
  elements.ownerPanel.hidden = true;
  restorePanelTrigger();
  state.ownerProject = null;
  announce("已关闭原 owner 验证面板。");
});

// -- lifecycle: archive, recycle bin, reference-safe delete (WB-12) -----

const LIFE_STATE_LABELS = {
  draft: "草稿",
  published: "已发布",
  archived: "已归档",
  trashed: "回收站",
};

function lifePath(suffix) {
  const project = state.lifeProject;
  return `/api/v1/projects/${project.projectId}${suffix}`;
}

function showLifeError(error, action) {
  elements.lifeError.hidden = false;
  elements.lifeError.textContent = describeFailure(error, action);
}

async function openLifecycle(project) {
  state.lifeProject = project;
  state.lifeSelected = null;
  elements.lifeHeading.textContent = `生命周期与回收站 · ${project.name}`;
  elements.lifeScope.textContent =
    `项目：${project.name} · 目录：${project.canonicalPath}`;
  elements.lifeError.hidden = true;
  elements.lifeDetail.hidden = true;
  elements.lifePanel.hidden = false;
  focusIntoPanel(elements.lifeHeading);
  await loadLifecycle();
  announce("已打开生命周期与回收站。");
}

let lifeRequestSeq = 0;

async function loadLifecycle() {
  const project = state.lifeProject;
  if (!project) return;
  // A filter change fires this again while an earlier fetch is still in
  // flight; only the newest response may render, so a slow earlier request
  // (e.g. the previous filter) cannot overwrite the list with a stale view.
  const requestSeq = (lifeRequestSeq += 1);
  try {
    const filter = elements.lifeFilter.value;
    const suffix = filter && filter !== "all" ? `?lifecycle=${filter}` : "";
    const payload = await api(lifePath("/lifecycle" + suffix));
    if (requestSeq !== lifeRequestSeq) return;
    state.lifeData = payload;
    elements.lifeError.hidden = true;
    elements.lifeProjectNote.textContent = payload.projectArchived
      ? "项目已归档：仍可查看与恢复其资产。"
      : `已发布 ${payload.counts.published} · 归档 ${payload.counts.archived} · ` +
        `回收站 ${payload.counts.trashed} · 草稿 ${payload.counts.draft}`;
    renderLifeList();
  } catch (error) {
    if (requestSeq !== lifeRequestSeq) return;
    showLifeError(error, "读取生命周期");
  }
}

function renderLifeList() {
  elements.lifeList.textContent = "";
  const data = state.lifeData;
  if (!data) return;
  const buckets = data.assets;
  const rows = [];
  for (const stateName of ["published", "archived", "trashed", "draft"]) {
    for (const asset of buckets[stateName] || []) rows.push(asset);
  }
  if (rows.length === 0) {
    const item = document.createElement("li");
    item.textContent =
      "该过滤条件下没有资产。切换到「全部」查看全部资产，或先在该项目里导入资产。";
    elements.lifeList.appendChild(item);
    return;
  }
  for (const asset of rows) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent =
      `${asset.name} · ${LIFE_STATE_LABELS[asset.lifecycle] || asset.lifecycle} · ${asset.kind}`;
    button.addEventListener("click", () => selectLifeAsset(asset));
    item.appendChild(button);
    elements.lifeList.appendChild(item);
  }
}

function selectLifeAsset(asset) {
  state.lifeSelected = asset;
  const transitions = [
    [elements.lifeArchive, ["draft", "published"]],
    [elements.lifeUnarchive, ["archived"]],
    [elements.lifeTrash, ["draft", "published", "archived"]],
    [elements.lifeRestore, ["trashed"]],
    [elements.lifeReferences, ["draft", "published", "archived", "trashed"]],
    [elements.lifeDelete, ["draft", "published", "archived", "trashed"]],
  ];
  for (const [button, states] of transitions) {
    button.hidden = !states.includes(asset.lifecycle);
    button.disabled = button.hidden;
  }
  elements.lifeDetail.hidden = false;
  elements.lifeDetailName.textContent = asset.name;
  elements.lifeDetailState.textContent =
    `当前：${LIFE_STATE_LABELS[asset.lifecycle] || asset.lifecycle} · ${asset.kind}`;
  elements.lifeRefsNote.textContent = "";
  elements.lifeRefs.textContent = "";
  elements.lifeDeleteConfirm.hidden = true;
}

async function lifeVerb(verb, body) {
  const project = state.lifeProject;
  const asset = state.lifeSelected;
  if (!project || !asset) return;
  try {
    await api(
      `/api/v1/projects/${project.projectId}/actions/assets/${asset.assetId}/${verb}`,
      {
        method: "POST",
        body: {
          operation: mutation(newOperationId(), {
            action: verb,
            assetId: asset.assetId,
          }),
          ...(body || {}),
        },
      }
    );
    elements.lifeError.hidden = true;
    await loadLifecycle();
    announce(`已执行 ${verb}。`);
  } catch (error) {
    showLifeError(error, verb);
  }
}

async function loadLifeReferences() {
  const project = state.lifeProject;
  const asset = state.lifeSelected;
  if (!project || !asset) return;
  try {
    const report = await api(
      `/api/v1/projects/${project.projectId}/assets/${asset.assetId}/references`
    );
    elements.lifeError.hidden = true;
    state.lifeRefReport = report;
    elements.lifeRefsNote.textContent =
      `实例 ${report.instances.length} · 依赖方 ${report.dependents.length} · ` +
      `派生/复制 ${report.lineageChildren.length} · 画布引用 ${report.canvasReferences.length} · ` +
      `跨项目副本 ${report.crossProjectCopies.length} · ` +
      `索引完整：${report.indexComplete ? "是" : "否"} · ` +
      `可删除：${report.deletable ? "是" : "否"}`;
    elements.lifeRefs.textContent = "";
    for (const dep of report.dependents) {
      const item = document.createElement("li");
      item.textContent = `依赖方：${dep.name}（${dep.kind}）第 ${dep.revisionNumber} 次修订`;
      elements.lifeRefs.appendChild(item);
    }
    for (const child of report.lineageChildren) {
      const item = document.createElement("li");
      item.textContent = `${child.relation}：${child.name}（${child.kind}）`;
      elements.lifeRefs.appendChild(item);
    }
    for (const ref of report.canvasReferences) {
      const item = document.createElement("li");
      item.textContent = `画布 ${ref.canvasName} · 画板 ${ref.boardId} · 节点 ${ref.nodeId}`;
      elements.lifeRefs.appendChild(item);
    }
    for (const copy of report.crossProjectCopies) {
      const item = document.createElement("li");
      item.textContent = `跨项目副本：项目 ${copy.projectId} · ${copy.mode}（不受删除影响）`;
      elements.lifeRefs.appendChild(item);
    }
    for (const boundary of report.boundaries) {
      const item = document.createElement("li");
      item.textContent = `边界：${boundary}`;
      elements.lifeRefs.appendChild(item);
    }
  } catch (error) {
    showLifeError(error, "读取引用影响");
  }
}

async function hardDeleteLifeAsset() {
  const asset = state.lifeSelected;
  if (!asset) return;
  await loadLifeReferences();
  const report = state.lifeRefReport;
  if (!report || !report.deletable) {
    announce("存在引用或索引不完整，无法永久删除；请先解除关联。");
    return;
  }
  elements.lifeDeleteConfirmBody.textContent =
    `「${asset.name}」将被永久删除：实例 ${report.instances.length} · ` +
    `依赖方 ${report.dependents.length} · ` +
    `派生/复制 ${report.lineageChildren.length} · ` +
    `画布引用 ${report.canvasReferences.length} · ` +
    `跨项目副本 ${report.crossProjectCopies.length}。` +
    "此操作不可逆：只清除工作台记录，不删除本地源文件，" +
    "也不影响已导出备份与跨项目副本。";
  elements.lifeDeleteConfirm.hidden = false;
  // Safe default: cancel holds focus until the maintainer chooses.
  elements.lifeDeleteCancel.focus();
}

async function confirmHardDeleteLifeAsset() {
  elements.lifeDeleteConfirm.hidden = true;
  await lifeVerb("hard-delete", { confirm: true });
  elements.lifeDetail.hidden = true;
  state.lifeSelected = null;
}

function cancelHardDeleteLifeAsset() {
  elements.lifeDeleteConfirm.hidden = true;
  announce("已取消永久删除。");
}

async function projectArchive(archived) {
  const project = state.lifeProject;
  if (!project) return;
  const verb = archived ? "project-archive" : "project-unarchive";
  try {
    await api(`/api/v1/projects/${project.projectId}/actions/${verb}`, {
      method: "POST",
      body: {
        operation: mutation(newOperationId(), { action: verb }),
      },
    });
    elements.lifeError.hidden = true;
    await loadLifecycle();
    announce(archived ? "项目已归档。" : "项目已取消归档。");
  } catch (error) {
    showLifeError(error, verb);
  }
}

elements.lifeReload.addEventListener("click", () => loadLifecycle());
elements.lifeFilter.addEventListener("change", () => loadLifecycle());
elements.lifeArchive.addEventListener("click", () => lifeVerb("archive"));
elements.lifeUnarchive.addEventListener("click", () => lifeVerb("unarchive"));
elements.lifeTrash.addEventListener("click", () => lifeVerb("trash"));
elements.lifeRestore.addEventListener("click", () => {
  const asset = state.lifeSelected;
  if (!asset) return;
  // A name clash is resolved by prompting; the server enforces uniqueness.
  lifeVerb("restore").catch(() => {});
});
elements.lifeReferences.addEventListener("click", loadLifeReferences);
elements.lifeDelete.addEventListener("click", hardDeleteLifeAsset);
elements.lifeDeleteCancel.addEventListener("click", cancelHardDeleteLifeAsset);
elements.lifeDeleteConfirmButton.addEventListener(
  "click",
  confirmHardDeleteLifeAsset
);
elements.lifePanel.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.lifeDeleteConfirm.hidden) {
    event.preventDefault();
    cancelHardDeleteLifeAsset();
  }
});
elements.lifeProjectArchive.addEventListener("click", () => projectArchive(true));
elements.lifeProjectUnarchive.addEventListener("click", () => projectArchive(false));
elements.lifeClose.addEventListener("click", () => {
  elements.lifePanel.hidden = true;
  restorePanelTrigger();
  state.lifeProject = null;
  announce("已关闭生命周期面板。");
});

// -- settings: consistency backup, verify, restore (WB-13) --------------

function showSettingsError(error, action) {
  elements.settingsError.hidden = false;
  elements.settingsError.textContent = describeFailure(error, action);
}

async function openSettings() {
  elements.settingsError.hidden = true;
  elements.settingsPanel.hidden = false;
  // This panel has no heading element reference; the panel itself is the
  // labelled focus target (aria-labelledby="settings-heading").
  focusIntoPanel(elements.settingsPanel);
  renderDiagnostics();
  announce("已打开设置与备份。");
}

function renderDiagnostics() {
  elements.settingsDiagnostics.textContent = "";
  const rows = [
    `已登记项目：${state.projects.length}`,
    `会话：${state.token ? "有效（内存中，不落盘）" : "无"}`,
    "备份不含 token/授权/源仓库；恢复到新目录后需重新授权。",
  ];
  for (const text of rows) {
    const item = document.createElement("li");
    item.textContent = text;
    elements.settingsDiagnostics.appendChild(item);
  }
}

async function createBackup() {
  const destination = elements.backupDest.value.trim();
  try {
    const payload = await api("/api/v1/backup", {
      method: "POST",
      body: {
        operation: mutation(newOperationId(), { action: "create" }),
        action: "create",
        ...(destination ? { destination } : {}),
      },
    });
    elements.settingsError.hidden = true;
    const result = payload.result;
    elements.backupNote.textContent =
      `已创建备份：${result.path} · schema v${result.schemaVersion} · ` +
      `blob ${result.blobCount} · ${result.bytes} 字节 · ` +
      `含凭证：${result.containsCredentials ? "是" : "否"} · ` +
      `含源仓库：${result.containsSourceRepo ? "是" : "否"}`;
    elements.backupVerifyPath.value = result.path;
    elements.restorePath.value = result.path;
    announce("已创建备份。");
  } catch (error) {
    showSettingsError(error, "创建备份");
  }
}

async function verifyBackup() {
  const path = elements.backupVerifyPath.value.trim();
  if (!path) return;
  try {
    const report = await api(`/api/v1/backup?path=${encodeURIComponent(path)}`);
    elements.settingsError.hidden = true;
    elements.backupVerifyNote.textContent =
      `校验通过 · schema v${report.schemaVersion} · blob ${report.blobCount} · ` +
      `含凭证：${report.containsCredentials ? "是" : "否"}`;
    announce("备份校验通过。");
  } catch (error) {
    elements.backupVerifyNote.textContent = "";
    showSettingsError(error, "校验备份");
  }
}

async function restoreBackup() {
  const path = elements.restorePath.value.trim();
  const target = elements.restoreTarget.value.trim();
  if (!path || !target) {
    announce("恢复需要备份包路径与新的空目录。");
    return;
  }
  try {
    const payload = await api("/api/v1/backup", {
      method: "POST",
      body: {
        operation: mutation(newOperationId(), { action: "restore" }),
        action: "restore",
        path,
        target,
      },
    });
    elements.settingsError.hidden = true;
    const result = payload.result;
    elements.restoreNote.textContent =
      `已恢复到 ${result.restoredDataDir} · schema v${result.schemaVersion} · ` +
      `blob ${result.blobCount} · 引用完整：${result.integrity.referencedBlobsPresent ? "是" : "否"} · ` +
      `已切换：${result.switched ? "是" : "否（原数据保留，切换为显式动作）"} · ` +
      `需重新授权：${result.reauthorizationRequired ? "是" : "否"}`;
    announce("已恢复到新目录（原数据保留）。");
  } catch (error) {
    elements.restoreNote.textContent = "";
    showSettingsError(error, "恢复备份");
  }
}

elements.backupCreate.addEventListener("click", createBackup);
elements.backupVerify.addEventListener("click", verifyBackup);
elements.restoreRun.addEventListener("click", restoreBackup);
elements.settingsClose.addEventListener("click", () => {
  elements.settingsPanel.hidden = true;
  restorePanelTrigger();
  announce("已关闭设置与备份。");
});
elements.settingsOpen.addEventListener("click", () => openSettings());

async function startSession() {
  const fragment = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : "";
  const params = new URLSearchParams(fragment);
  const bootstrap = params.get("bootstrap") || "";
  if (!bootstrap) {
    failSession("地址中没有一次性 bootstrap 内容。请使用启动时打印的链接。");
    return;
  }
  // Clear the fragment before the exchange completes so the one-time
  // secret never stays in the address bar, history, or a bookmark.
  window.history.replaceState(
    null,
    "",
    window.location.pathname + window.location.search
  );
  try {
    const payload = await api("/api/v1/session", {
      method: "POST",
      body: { bootstrap },
    });
    state.token = payload.token;
    setSessionState(
      `会话有效 · 至 ${formatLocalTime(payload.expiresAt)}`,
      "ready",
      `服务端时间 ${payload.expiresAt}`
    );
    elements.sessionError.hidden = true;
    await loadProjects();
  } catch (error) {
    failSession(
      error.status === 401
        ? "bootstrap 内容无效、已被使用或已过期。请重新启动服务并打开新链接。"
        : "无法建立会话：" + error.message
    );
  }
}

elements.probeForm.addEventListener("submit", onProbe);
elements.registerForm.addEventListener("submit", onRegister);
elements.cancelCandidate.addEventListener("click", () => {
  resetCandidate();
  announce("已取消登记。");
  elements.projectPath.focus();
});
elements.refreshButton.addEventListener("click", () => {
  loadProjects();
  announce("已重新探测项目连接状态。");
});
elements.sessionError.hidden = true;

startSession();

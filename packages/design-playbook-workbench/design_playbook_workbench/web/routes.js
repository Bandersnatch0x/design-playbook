// Generated from design_playbook_workbench/client_routes.py by
// scripts/generate_workbench_routes.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.workbenchRoutes = {
    API: "/api/v1",
    STATUS: "/api/v1/status",
    RESOLVE: "/api/v1/resolve",
    PROJECTS: "/api/v1/projects",
    PROBE: "/api/v1/projects/probe",
    BACKUP: "/api/v1/backup",
    SESSION: "/api/v1/session",
    project: function (project) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "";
    },
    projectAction: function (project, action) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/actions/" + encodeURIComponent(action) + "";
    },
    assets: function (project) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/assets";
    },
    asset: function (project, asset) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/assets/" + encodeURIComponent(asset) + "";
    },
    assetAction: function (project, asset, verb) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/actions/assets/" + encodeURIComponent(asset) + "/" + encodeURIComponent(verb) + "";
    },
    assetPreview: function (project, asset) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/assets/" + encodeURIComponent(asset) + "/preview";
    },
    assetDocument: function (project, asset, view) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/assets/" + encodeURIComponent(asset) + "/document/" + encodeURIComponent(view) + "";
    },
    assetTokens: function (project, asset, view) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/assets/" + encodeURIComponent(asset) + "/tokens/" + encodeURIComponent(view) + "";
    },
    assetReferences: function (project, asset) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/assets/" + encodeURIComponent(asset) + "/references";
    },
    proposals: function (project) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/proposals";
    },
    proposal: function (project, proposal) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/proposals/" + encodeURIComponent(proposal) + "";
    },
    proposalAction: function (project, proposal, verb) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/actions/proposals/" + encodeURIComponent(proposal) + "/" + encodeURIComponent(verb) + "";
    },
    instances: function (project) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/instances";
    },
    canvases: function (project) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/canvases";
    },
    canvas: function (project, canvas) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/canvases/" + encodeURIComponent(canvas) + "";
    },
    canvasAction: function (project, canvas, verb) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/actions/canvases/" + encodeURIComponent(canvas) + "/" + encodeURIComponent(verb) + "";
    },
    requests: function (project) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/requests";
    },
    requestAction: function (project, request, verb) {
      return "/api/v1/projects/" + encodeURIComponent(project) + "/actions/requests/" + encodeURIComponent(request) + "/" + encodeURIComponent(verb) + "";
    },
    backupPath: function (path) {
      return "/api/v1/backup?path=" + encodeURIComponent(path) + "";
    },
  };
})(window);

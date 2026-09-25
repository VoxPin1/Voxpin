const SECRET = "9wYmqDcEu9QOshmVcbuIyQ";
const DOCUMENT_ID = "1dReqYodsf53bGHCZMvZzoxCcWDqSbux4Fofj5hJ5LY8";
const TRANSLATIONS_DOCUMENT_ID = "1pC-qGeyFBYQv93zwTt15dQTiMnJz6yCgQYGWPQwiCoc";
const PREORDER_SHEET_ID = "1rb1h6YdbB8J5fJFvYC_bsjiuh4KisbZFvPbl5vInGV8";

function doPost(e) {
  try {
    const data = parseBody(e);
    if (data.kind === "preorder") {
      return savePreorder(data);
    }

    if (data.secret !== SECRET) {
      return jsonOut({ ok: false, error: "bad secret" });
    }

    const kind = data.kind || "note";
    const docId =
      data.document_id ||
      data.documentId ||
      (kind === "translate" ? TRANSLATIONS_DOCUMENT_ID : DOCUMENT_ID);
    const dayTitle = data.day || formatDay(new Date());
    const result = bodyForDay(docId, dayTitle);
    result.body.appendParagraph(data.text);
    return jsonOut({
      ok: true,
      tab: dayTitle,
      mode: result.mode,
      kind: kind,
      document_id: docId,
    });
  } catch (err) {
    return jsonOut({ ok: false, error: String(err) });
  }
}

function doGet(e) {
  return doPost(e);
}

function parseBody(e) {
  if (e && e.postData && e.postData.contents) {
    try {
      return JSON.parse(e.postData.contents);
    } catch (err) {
      // Fall through to form fields.
    }
  }
  return (e && e.parameter) || {};
}

function savePreorder(data) {
  const name = String(data.name || "").trim();
  const email = String(data.email || "").trim();
  if (!name || !email) {
    return jsonOut({ ok: false, error: "name and email are required" });
  }
  const sheet = SpreadsheetApp.openById(PREORDER_SHEET_ID).getSheets()[0];
  ensurePreorderHeaders(sheet);
  sheet.appendRow([
    new Date(),
    name,
    email,
    String(data.version || ""),
    String(data.count || ""),
    String(data.features || data.feature || ""),
    String(data.notes || ""),
  ]);
  return jsonOut({ ok: true, kind: "preorder" });
}

function ensurePreorderHeaders(sheet) {
  const headers = [
    "Timestamp",
    "Name",
    "Email",
    "Version",
    "Count",
    "Features",
    "Notes",
  ];
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
    return;
  }
  const first = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  if (!String(first[0] || "").trim()) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
}

function jsonOut(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function formatDay(date) {
  return Utilities.formatDate(date, Session.getScriptTimeZone(), "MMM d, yyyy");
}

function findTab(doc, title) {
  const tabs = doc.getTabs();
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].getTitle() === title) {
      return tabs[i];
    }
  }
  return null;
}

function createDayTab(docId, title) {
  const token = ScriptApp.getOAuthToken();
  const url = "https://docs.googleapis.com/v1/documents/" + docId + ":batchUpdate";
  const resp = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + token },
    payload: JSON.stringify({
      requests: [{ addDocumentTab: { tabProperties: { title: title } } }]
    }),
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  if (resp.getResponseCode() >= 300) {
    throw new Error(text);
  }
}

function ensureDayHeading(body, title) {
  const paras = body.getParagraphs();
  for (let i = 0; i < paras.length; i++) {
    if (
      paras[i].getHeading() === DocumentApp.ParagraphHeading.HEADING1 &&
      paras[i].getText() === title
    ) {
      return;
    }
  }
  body.appendParagraph(title).setHeading(DocumentApp.ParagraphHeading.HEADING1);
}

function bodyForDay(docId, title) {
  let doc = DocumentApp.openById(docId);
  let tab = findTab(doc, title);
  if (!tab) {
    try {
      createDayTab(docId, title);
      doc = DocumentApp.openById(docId);
      tab = findTab(doc, title);
    } catch (err) {
      ensureDayHeading(doc.getBody(), title);
      return { body: doc.getBody(), mode: "heading:" + String(err) };
    }
  }
  if (tab) {
    return { body: tab.asDocumentTab().getBody(), mode: "tab" };
  }
  ensureDayHeading(doc.getBody(), title);
  return { body: doc.getBody(), mode: "heading" };
}

function authorize() {
  UrlFetchApp.fetch("https://www.google.com");
}

function authorizeSheets() {
  SpreadsheetApp.openById(PREORDER_SHEET_ID).getName();
}

const SECRET = "9wYmqDcEu9QOshmVcbuIyQ";
const DOCUMENT_ID = "1dReqYodsf53bGHCZMvZzoxCcWDqSbux4Fofj5hJ5LY8";

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== SECRET) {
      return jsonOut({ ok: false, error: "bad secret" });
    }

    const dayTitle = data.day || formatDay(new Date());
    const result = bodyForDay(DOCUMENT_ID, dayTitle);
    result.body.appendParagraph(data.text);
    return jsonOut({ ok: true, tab: dayTitle, mode: result.mode });
  } catch (err) {
    return jsonOut({ ok: false, error: String(err) });
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

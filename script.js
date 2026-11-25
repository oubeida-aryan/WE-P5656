// WI-PRESENCE | CNC HOSPITAL
// Google Apps Script backend and mobile QR check-in page.

const SECRET_KEY = "HOSPITAL_STAFF_SECRET_2024";
const TIMEZONE = "Africa/Nouakchott";
const STEP_SECONDS = 15;
const TOTAL_RESIDENTS_ESTIMATED = 30;
const DEFAULT_REPORT_EMAIL = "aryanoubeida@gmail.com";

function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function getConfiguredEmail() {
  return PropertiesService.getScriptProperties().getProperty("CHEF_EMAIL") || DEFAULT_REPORT_EMAIL;
}

function isEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getSheets() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  let presence = spreadsheet.getSheetByName("Presence");
  let residents = spreadsheet.getSheetByName("Residents");

  if (!presence) {
    presence = spreadsheet.insertSheet("Presence");
    presence.appendRow(["Date", "Heure", "Nom resident", "ID telephone"]);
    presence.getRange(1, 1, 1, 4).setFontWeight("bold").setBackground("#d9ead3");
    presence.setFrozenRows(1);
    presence.getRange("A:A").setNumberFormat("dd/MM/yyyy");
    presence.getRange("B:B").setNumberFormat("HH:mm:ss");
  }

  if (!residents) {
    residents = spreadsheet.insertSheet("Residents");
    residents.appendRow(["ID telephone", "Nom resident", "Date inscription"]);
    residents.getRange(1, 1, 1, 3).setFontWeight("bold").setBackground("#cfe2f3");
    residents.setFrozenRows(1);
  }

  return { presence, residents };
}

function displayedRows(sheet) {
  return sheet.getDataRange().getDisplayValues();
}

function attendanceRows_(sheet) {
  const range = sheet.getDataRange();
  const rows = range.getDisplayValues();
  const values = range.getValues();
  const zone = TIMEZONE;
  for (let i = 1; i < rows.length; i++) {
    if (values[i][0] instanceof Date) {
      rows[i][0] = Utilities.formatDate(values[i][0], zone, "dd/MM/yyyy");
    }
  }
  return rows;
}

function getQrPayload_() {
  const serverEpoch = Math.floor(Date.now() / 1000);
  const step = currentStep(serverEpoch);
  return {
    ok: true,
    token: computeHmac_(String(step)),
    ts: serverEpoch,
    serverEpoch: serverEpoch,
    serverTime: Utilities.formatDate(new Date(serverEpoch * 1000), TIMEZONE, "yyyy-MM-dd HH:mm:ss"),
    timezone: TIMEZONE,
  };
}

function getAudit_() {
  const { presence, residents } = getSheets();
  const serverEpoch = Math.floor(Date.now() / 1000);
  return {
    ok: true,
    serverEpoch: serverEpoch,
    serverTime: Utilities.formatDate(new Date(serverEpoch * 1000), TIMEZONE, "yyyy-MM-dd HH:mm:ss"),
    timezone: TIMEZONE,
    schedule: "Lundi, mardi et jeudi 07:30-08:30 GMT",
    qrIssuedBy: "Google Apps Script server",
    presenceRows: Math.max(presence.getLastRow() - 1, 0),
    registeredPhones: Math.max(residents.getLastRow() - 1, 0),
  };
}

function checkOrRecord(deviceId, residentName, token, timestamp) {
  if (!isValidQrToken(token, timestamp)) {
    throw new Error("Code expire. Rescannez le QR affiche par le staff.");
  }

  const cleanDeviceId = String(deviceId || "").trim();
  const cleanName = String(residentName || "").trim();
  if (!cleanDeviceId || cleanDeviceId.length > 128 || /^[=+@-]/.test(cleanDeviceId)) {
    throw new Error("Identifiant de telephone invalide.");
  }
  if (cleanName.length > 120 || /^[=+@-]/.test(cleanName)) {
    throw new Error("Nom invalide.");
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    return recordPresence_(cleanDeviceId, cleanName);
  } finally {
    SpreadsheetApp.flush();
    lock.releaseLock();
  }
}

function recordPresence_(deviceId, residentName) {
  const { presence, residents } = getSheets();
  const residentRows = displayedRows(residents);
  let registeredName = "";

  for (let i = 1; i < residentRows.length; i++) {
    if (String(residentRows[i][0]).trim() === deviceId) {
      registeredName = String(residentRows[i][1]).trim();
      break;
    }
  }

  const now = new Date();
  const dateText = Utilities.formatDate(now, TIMEZONE, "dd/MM/yyyy");
  const timeText = Utilities.formatDate(now, TIMEZONE, "HH:mm:ss");

  if (!registeredName) {
    if (!residentName) return { status: "NEED_NAME" };
    registeredName = residentName;
    residents.appendRow([deviceId, registeredName, dateText + " " + timeText]);
  }

  const presenceRows = attendanceRows_(presence);
  for (let i = presenceRows.length - 1; i >= 1; i--) {
    const row = presenceRows[i];
    const sameDay = String(row[0]).trim() === dateText;
    const sameDevice = String(row[3]).trim() === deviceId;
    const sameName = String(row[2]).trim() === registeredName;
    if (sameDay && (sameDevice || sameName)) {
      return { status: "ALREADY_PRESENT", name: registeredName, time: String(row[1]).trim() };
    }
  }

  presence.appendRow([dateText, timeText, registeredName, deviceId]);
  return { status: "SUCCESS", name: registeredName, time: timeText };
}

function getLiveStatus_() {
  const { presence, residents } = getSheets();
  const today = Utilities.formatDate(new Date(), TIMEZONE, "dd/MM/yyyy");
  const rows = attendanceRows_(presence);
  const todayPresences = [];

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]).trim() !== today) continue;
    todayPresences.push({
      name: String(rows[i][2]).trim(),
      time: String(rows[i][1]).trim(),
    });
  }

  return {
    count: todayPresences.length,
    total: Math.max(residents.getLastRow() - 1, TOTAL_RESIDENTS_ESTIMATED),
    recent: todayPresences.slice(-3).reverse(),
    lastScan: todayPresences.length ? todayPresences[todayPresences.length - 1] : null,
  };
}

function computeHmac_(data) {
  const signature = Utilities.computeHmacSha256Signature(data, SECRET_KEY);
  return signature.map(byte => ("0" + (byte & 0xFF).toString(16)).slice(-2)).join("");
}

function currentStep(timestamp) {
  return Math.floor(Number(timestamp) / STEP_SECONDS);
}

function isValidQrToken(token, timestamp) {
  if (!token || !timestamp || !Number.isFinite(Number(timestamp))) return false;
  const step = currentStep(timestamp);
  const nowStep = currentStep(Date.now() / 1000);
  return Math.abs(nowStep - step) <= 2 && token === computeHmac_(String(step));
}

function isValidAdminAction(action, token, timestamp, email) {
  if (!token || !timestamp || !Number.isFinite(Number(timestamp))) return false;
  const step = currentStep(timestamp);
  const nowStep = currentStep(Date.now() / 1000);
  const message = action + ":" + String(email || "") + ":" + step;
  return Math.abs(nowStep - step) <= 2 && token === computeHmac_(message);
}

function doGet(event) {
  const params = (event && event.parameter) || {};
  const action = String(params.action || "");

  if (action === "getQr") return jsonResponse(getQrPayload_());
  if (action === "audit") {
    try {
      return jsonResponse(getAudit_());
    } catch (error) {
      return jsonResponse({ ok: false, error: String(error && error.message ? error.message : error) });
    }
  }
  if (action === "getLiveStatus") {
    try {
      return jsonResponse(getLiveStatus_());
    } catch (error) {
      return jsonResponse({ ok: false, error: String(error && error.message ? error.message : error) });
    }
  }
  if (["setReportEmail", "sendReport"].includes(action)) {
    if (!isValidAdminAction(action, params.token, params.ts, params.email)) {
      return jsonResponse({ ok: false, error: "Action non autorisee ou expiree." });
    }

    try {
      if (!isEmail(params.email)) throw new Error("Adresse e-mail invalide.");

      if (action === "setReportEmail") {
        PropertiesService.getScriptProperties().setProperty("CHEF_EMAIL", params.email.trim());
        return jsonResponse({ ok: true });
      }

      return jsonResponse({ ok: true, ...sendDailyReportTo_(params.email) });
    } catch (error) {
      return jsonResponse({
        ok: false,
        error: String(error && error.message ? error.message : error),
      });
    }
  }

  const token = String(params.token || "");
  const timestamp = Number(params.ts);
  if (!isValidQrToken(token, timestamp)) {
    return HtmlService.createHtmlOutput(
      "<div style='font-family:Arial,sans-serif;text-align:center;padding:60px 20px;color:#071C33'>" +
      "<h2 style='color:#C81E3A'>QR code expire</h2>" +
      "<p>Veuillez rescanner le QR affiche par le staff.</p></div>"
    ).addMetaTag("viewport", "width=device-width, initial-scale=1");
  }

  return HtmlService.createHtmlOutput(getHtml_(token, timestamp))
    .setTitle("WI-PRESENCE - CNC")
    .addMetaTag("viewport", "width=device-width, initial-scale=1")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function authorizeReports() {
  getSheets();
  return MailApp.getRemainingDailyQuota();
}

function sendDailyReport() {
  return sendDailyReportTo_(getConfiguredEmail());
}

function sendDailyReportTo_(recipientEmail) {
  const { presence, residents } = getSheets();
  const dateText = Utilities.formatDate(new Date(), TIMEZONE, "dd/MM/yyyy");
  const targetEmail = isEmail(recipientEmail) ? String(recipientEmail).trim() : getConfiguredEmail();
  if (!isEmail(targetEmail)) throw new Error("Aucune adresse e-mail valide n'est configuree.");

  const residentRows = displayedRows(residents);
  const presenceRows = attendanceRows_(presence);
  const presentByName = Object.create(null);

  for (let i = 1; i < presenceRows.length; i++) {
    if (String(presenceRows[i][0]).trim() !== dateText) continue;
    // Use the displayed cell to prevent a second timezone conversion.
    presentByName[String(presenceRows[i][2]).trim()] = String(presenceRows[i][1]).trim();
  }

  let rowsHtml = "";
  let presentCount = 0;
  const totalResidents = Math.max(0, residentRows.length - 1);

  for (let i = 1; i < residentRows.length; i++) {
    const name = String(residentRows[i][1]).trim();
    const time = presentByName[name];
    if (time) {
      presentCount++;
      rowsHtml += `<tr class="present"><td>${escapeHtml(name)}</td><td>Present - ${escapeHtml(time)} GMT</td></tr>`;
    } else {
      rowsHtml += `<tr class="absent"><td>${escapeHtml(name)}</td><td>Absent</td></tr>`;
    }
  }

  const rate = totalResidents ? Math.round((presentCount / totalResidents) * 100) : 0;
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:Arial,sans-serif;padding:28px;color:#102A43}
    .header{border-bottom:3px solid #22D3D1;padding-bottom:14px;margin-bottom:20px}
    h1{color:#071C33;margin:0;font-size:24px}.sub{color:#60758A;margin-top:6px;font-size:13px}
    .stats{background:#EFF9F8;border:1px solid #B6E9E7;padding:14px;border-radius:8px;margin-bottom:20px}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:11px;border:1px solid #D9E2EC;text-align:left}
    th{background:#F3F7FA}.present{background:#F0FDF4;color:#087F5B}.absent{background:#FFF5F5;color:#C81E3A}
    .footer{margin-top:30px;color:#829AB1;font-size:11px;text-align:right}
  </style></head><body>
    <div class="header"><h1>WI-PRESENCE | CNC HOSPITAL</h1><div class="sub">FEUILLE DE PRESENCE DU STAFF - ${dateText} - GMT</div></div>
    <div class="stats"><b>Taux de presence :</b> ${presentCount} / ${totalResidents} (${rate}%)</div>
    <table><thead><tr><th>Nom et prenom</th><th>Statut / heure</th></tr></thead><tbody>${rowsHtml || "<tr><td colspan='2'>Aucun resident enregistre.</td></tr>"}</tbody></table>
    <div class="footer">Rapport genere par WI-PRESENCE CNC.</div>
  </body></html>`;

  const pdf = Utilities.newBlob(html, "text/html", "rapport.html")
    .getAs("application/pdf")
    .setName(`WI_PRESENCE_${dateText.replace(/\//g, "-")}.pdf`);

  MailApp.sendEmail({
    to: targetEmail,
    subject: `[WI-PRESENCE] Rapport du ${dateText} (${rate}%)`,
    body: `Bonjour,\n\nVeuillez trouver le rapport WI-PRESENCE du ${dateText}.\nPresence : ${presentCount} / ${totalResidents} (${rate}%).\n\nCordialement,\nCNC Hospital`,
    attachments: [pdf],
  });

  return { recipient: targetEmail, date: dateText, presentCount, totalResidents, rate };
}

function getHtml_(token, timestamp) {
  return String.raw`<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#F3F7FA;color:#071C33;margin:0;padding:22px}
    .card{background:#fff;border:1px solid #DBE7EF;border-radius:22px;padding:26px 22px;max-width:420px;margin:18px auto;box-shadow:0 16px 40px rgba(7,28,51,.1)}
    .brand{color:#087F82;font-size:12px;font-weight:800;letter-spacing:.08em}.title{font-size:24px;font-weight:800;margin:8px 0 4px}.sub{color:#60758A;font-size:14px;line-height:1.5}
    input{width:100%;padding:14px 15px;margin:20px 0 12px;border:1px solid #CBD9E3;border-radius:12px;font-size:16px;outline:none}input:focus{border-color:#22D3D1;box-shadow:0 0 0 3px rgba(34,211,209,.16)}
    button{width:100%;background:#071C33;color:#fff;border:0;padding:14px;border-radius:12px;font-size:16px;font-weight:800;cursor:pointer}.small{font-size:13px;color:#60758A}.result{border-radius:15px;padding:18px;text-align:center;margin-top:18px}.success{background:#ECFDF5;border:1px solid #A7F3D0}.warning{background:#FFFBEB;border:1px solid #FDE68A}.badge{font-size:30px}.name{font-size:20px;font-weight:800;margin:7px 0}.time{color:#087F5B;font-weight:800;font-size:15px}
  </style></head><body><div class="card"><div class="brand">WI-PRESENCE | CNC</div><div class="title">Pointage du staff</div><div class="sub">Validez votre presence en quelques secondes.</div>
    <div id="loader" class="small" style="padding:24px 0">Validation en cours...</div>
    <div id="registerBox" style="display:none"><p class="small">Premiere connexion sur cet appareil. Entrez votre nom complet.</p><input id="nameInput" type="text" placeholder="Dr. Nom Prenom" autocomplete="name"><button onclick="submitName()">Valider ma presence</button></div>
    <div id="resultBox" style="display:none"></div></div><script>
      const storageKey = "hospital_device_id";
      const deviceId = localStorage.getItem(storageKey) || localStorage.getItem("wi_presence_device_id") || "DEV_" + crypto.randomUUID();
      localStorage.setItem(storageKey, deviceId);
      const qrToken=${JSON.stringify(token)};const qrTimestamp=${Number(timestamp)};
      function sendCheck(name){google.script.run.withSuccessHandler(onSuccess).withFailureHandler(onError).checkOrRecord(deviceId,name||"",qrToken,qrTimestamp)}
      function onSuccess(res){const loader=document.getElementById("loader"),register=document.getElementById("registerBox"),box=document.getElementById("resultBox");loader.style.display="none";if(res.status==="NEED_NAME"){register.style.display="block";return}register.style.display="none";box.style.display="block";const success=res.status==="SUCCESS";box.innerHTML='<div class="result '+(success?'success':'warning')+'"><div class="badge">'+(success?'✓':'!')+'</div><div class="name">'+safe(res.name)+'</div><div class="time">'+(success?'Presence validee':'Deja note present')+' - '+safe(res.time)+' GMT</div></div>'}
      function onError(error){document.getElementById("loader").innerHTML='<span style="color:#C81E3A">Erreur : '+safe(error&&error.message||error)+'</span>'}
      function submitName(){const input=document.getElementById("nameInput"),value=input.value.trim();if(!value){input.focus();return}document.getElementById("registerBox").style.display="none";document.getElementById("loader").style.display="block";sendCheck(value)}
      function safe(value) {
        const element = document.createElement("span");
        element.textContent = String(value == null ? "" : value);
        return element.innerHTML;
      }
      window.onload = () => sendCheck("");
    </script></body></html>`;
}

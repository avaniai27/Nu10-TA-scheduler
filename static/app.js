
const $ = (id) => document.getElementById(id);

let interviews = [];
let slotCount = 0;
let openDetailId = null;
let dashboardStarted = false;

function showNotice(message, type = "success") {
  const el = $("notice");
  if (!el) return;
  el.textContent = message;
  el.className = `notice ${type}`;
}

function localDateTimeValue(date) {
  const p = n => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
}

function addSlot(value = "") {
  const container = $("slots");
  if (!container || container.children.length >= 10) {
    showNotice("You can add up to 10 slots.", "error");
    return;
  }

  slotCount++;
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(10, 0, 0, 0);

  const wrapper = document.createElement("div");
  wrapper.className = "slot";
  wrapper.innerHTML = `
    <div class="slot-top">
      <span>Slot ${slotCount}</span>
      <button type="button" class="remove">Remove</button>
    </div>
    <div class="slot-fields">
      <label>Date and time (your local time)
        <input class="slot-datetime" type="datetime-local" required>
      </label>
      <div class="muted" style="align-self:end;padding-bottom:12px">
        Time displays in AM/PM in email.
      </div>
    </div>`;

  wrapper.querySelector("input").value = value || localDateTimeValue(d);
  wrapper.querySelector(".remove").addEventListener("click", () => {
    wrapper.remove();
    renumberSlots();
  });

  container.appendChild(wrapper);
  renumberSlots();
}

function renumberSlots() {
  const container = $("slots");
  if (!container) return;

  [...container.children].forEach((node, i) => {
    const label = node.querySelector(".slot-top span");
    if (label) label.textContent = `Slot ${i + 1}`;
  });
  slotCount = container.children.length;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[c]));
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin"
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || `Request failed (${response.status})`
    );
  }

  return data;
}

function displayStatus(iv) {
  const raw = String(iv.status || "").trim().toLowerCase();

  if (raw.includes("failed") && iv.selected_slot) {
    return "Scheduled · email issue";
  }
  if (raw.includes("failed")) return "Email failed";
  if (raw.includes("confirmation email issue")) {
    return "Scheduled · confirmation pending";
  }
  if (iv.selected_slot || raw === "interview scheduled") {
    return "Scheduled";
  }
  if (raw.includes("awaiting candidate selection") ||
      raw.includes("awaiting selection")) {
    return "Awaiting selection";
  }
  if (raw.includes("invitation queued")) return "Invitation queued";

  return iv.status || "Status unavailable";
}

function statusTone(iv) {
  const label = displayStatus(iv).toLowerCase();

  if (label === "scheduled") return "scheduled";
  if (label.includes("failed") || label.includes("issue")) return "failed";
  if (label.includes("pending")) return "warning";
  if (label.includes("awaiting")) return "waiting";
  if (label.includes("queued")) return "queued";

  return "";
}

async function loadInterviews() {
  const tbody = $("interviewRows");
  const data = await api("/api/interviews");

  if (!Array.isArray(data)) {
    throw new Error("Unexpected interview list returned by the server.");
  }

  interviews = data;

  if ($("totalCount")) {
    $("totalCount").textContent = data.length;
  }
  if ($("waitingCount")) {
    $("waitingCount").textContent = data.filter(iv =>
      !iv.selected_slot &&
      !String(iv.status || "").toLowerCase().includes("failed")
    ).length;
  }
  if ($("scheduledCount")) {
    $("scheduledCount").textContent =
      data.filter(iv => Boolean(iv.selected_slot)).length;
  }

  if (!tbody) return;

  if (data.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="5">No interviews yet. Create an interview invitation above.</td></tr>';
  } else {
    tbody.innerHTML = "";

    data.forEach(iv => {
      const tr = document.createElement("tr");
      const isOpen = Number(openDetailId) === Number(iv.id);

      tr.innerHTML = `
        <td>${escapeHtml(iv.candidate_name)}<br>
          <span class="muted">${escapeHtml(iv.candidate_email)}</span>
        </td>
        <td>${escapeHtml(iv.job_title)}</td>
        <td><span class="status ${statusTone(iv)}">${escapeHtml(displayStatus(iv))}</span></td>
        <td>${iv.created_at ? new Date(iv.created_at).toLocaleString() : "—"}</td>
        <td><button type="button" class="outline" data-detail="${Number(iv.id)}">${isOpen ? "Hide" : "View"}</button></td>`;

      tbody.appendChild(tr);
    });
  }

  tbody.querySelectorAll("[data-detail]").forEach(button => {
    button.addEventListener("click", () => {
      toggleDetail(Number(button.dataset.detail));
    });
  });

  if (openDetailId !== null) {
    renderDetail(openDetailId, false);
  }
}

function toggleDetail(id) {
  if (Number(openDetailId) === Number(id)) {
    hideDetail();
    return;
  }

  openDetailId = id;
  renderDetail(id, true);
  updateDetailButtons();
}

function hideDetail() {
  openDetailId = null;

  const detail = $("detail");
  if (detail) {
    detail.classList.add("hidden");
    detail.innerHTML = "";
  }

  updateDetailButtons();
}

function updateDetailButtons() {
  document.querySelectorAll("[data-detail]").forEach(button => {
    button.textContent =
      Number(button.dataset.detail) === Number(openDetailId)
        ? "Hide"
        : "View";
  });
}

function renderDetail(id, scrollToPanel = false) {
  const iv = interviews.find(x => Number(x.id) === Number(id));

  if (!iv) {
    hideDetail();
    return;
  }

  const slots = (iv.slots || []).map(s => {
    const selected = iv.selected_slot === s.datetime;
    const parsedDate = new Date(s.datetime);
    const time = Number.isNaN(parsedDate.getTime())
      ? s.datetime
      : parsedDate.toLocaleString();

    return `<li>${escapeHtml(time)}${selected ? " — Selected" : ""}</li>`;
  }).join("");

  const detail = $("detail");
  if (!detail) return;

  detail.innerHTML = `
    <div class="detail-heading">
      <div>
        <h3>Interview #${Number(iv.id)}</h3>
        <span class="status ${statusTone(iv)}">${escapeHtml(displayStatus(iv))}</span>
      </div>
      <button type="button" class="outline" id="hideDetailBtn">Hide details</button>
    </div>
    <div class="detail-grid">
      <div><b>Candidate</b><br>${escapeHtml(iv.candidate_name)}</div>
      <div><b>Candidate email</b><br>${escapeHtml(iv.candidate_email)}</div>
      <div><b>Phone</b><br>${escapeHtml(iv.candidate_phone || "Not provided")}</div>
      <div><b>Job title</b><br>${escapeHtml(iv.job_title)}</div>
      <div><b>Interviewer</b><br>${escapeHtml(iv.interviewer_name)}</div>
      <div><b>Interviewer email</b><br>${escapeHtml(iv.interviewer_email)}</div>
      <div><b>Invitation email</b><br>${iv.invitation_sent ? "Sent" : "Not sent / failed"}</div>
      <div><b>Confirmation emails</b><br>${iv.confirmation_sent ? "Sent" : "Pending or failed"}</div>
      <div><b>Selected time</b><br>${escapeHtml(iv.selected_slot_display || "Awaiting candidate")}</div>
    </div>
    <p><b>Offered slots</b></p>
    <ul>${slots || "<li>No slots available.</li>"}</ul>
    ${iv.meeting_url ? `<p><b>Meeting link:</b> <a target="_blank" rel="noopener" href="${escapeHtml(iv.meeting_url)}">${escapeHtml(iv.meeting_url)}</a></p>` : ""}
    ${iv.last_error ? `<p class="detail-error"><b>Last error:</b> ${escapeHtml(iv.last_error)}</p>` : ""}
    ${!iv.selected_slot ? `<div class="detail-actions"><button type="button" class="primary" id="resendBtn">Resend invitation</button></div>` : ""}
  `;

  detail.classList.remove("hidden");
  $("hideDetailBtn")?.addEventListener("click", hideDetail);

  $("resendBtn")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Resending…";

    try {
      await api(`/api/interviews/${Number(id)}/resend`, {
        method: "POST"
      });

      showNotice("Invitation resend request completed.", "success");
      await loadInterviews();
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      const current = $("resendBtn");
      if (current) {
        current.disabled = false;
        current.textContent = "Resend invitation";
      }
    }
  });

  if (scrollToPanel) {
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

$("addSlot")?.addEventListener("click", () => addSlot());

if ($("slots") && $("slots").children.length === 0) {
  addSlot();
}

$("mockBtn")?.addEventListener("click", () => {
  $("candidate_name").value = "Priya Sharma";
  $("candidate_email").value = "";
  $("candidate_phone").value = "+91 98765 43210";
  $("job_title").value = "AI Engineer";
  $("interviewer_name").value = "Rahul Mehta";
  $("interviewer_email").value = "";

  $("candidate_email").focus();

  showNotice(
    "Sample details filled. Enter the real candidate and interviewer email addresses before sending.",
    "success"
  );
});

$("refreshBtn")?.addEventListener("click", async () => {
  try {
    await loadInterviews();
    showNotice("Interview statuses refreshed.", "success");
  } catch (error) {
    showNotice("Could not refresh statuses: " + error.message, "error");
  }
});


$("interviewForm")?.addEventListener("submit", async event => {
  event.preventDefault();

  const form = $("interviewForm");
  const button = $("submitBtn");
  const slotInputs = [...document.querySelectorAll(".slot-datetime")];

  if (!slotInputs.length) {
    showNotice("Add at least one interview slot.", "error");
    return;
  }

  const slots = [];

  for (const input of slotInputs) {
    if (!input.value) {
      showNotice("Fill in every slot or remove the empty slot.", "error");
      return;
    }

    const date = new Date(input.value);

    if (Number.isNaN(date.getTime()) || date <= new Date()) {
      showNotice("Every interview slot must be in the future.", "error");
      return;
    }

    slots.push({ datetime: date.toISOString() });
  }

  const payload = {
    candidate_name: $("candidate_name").value.trim(),
    candidate_email: $("candidate_email").value.trim(),
    candidate_phone: $("candidate_phone").value.trim(),
    job_title: $("job_title").value.trim(),
    interviewer_name: $("interviewer_name").value.trim(),
    interviewer_email: $("interviewer_email").value.trim(),
    slots
  };

  if (!payload.candidate_email || !payload.interviewer_email ||
      !payload.candidate_name || !payload.job_title ||
      !payload.interviewer_name) {
    showNotice("Please fill in all required fields.", "error");
    return;
  }

  if (button) {
    button.disabled = true;
    button.textContent = "Sending invitation...";
  }

  showNotice("Saving interview and sending invitation...", "warning");

  try {
    const result = await api("/interviews/start", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    // Refresh the dashboard even if the email failed.
    await loadInterviews().catch(() => {});

    if (result.email_sent === true) {
      showNotice(
        `Email service accepted the invitation for ${payload.candidate_email}. Check Inbox and Spam.`,
        "success"
      );

      form.reset();
      $("slots").innerHTML = "";
      slotCount = 0;
      addSlot();
    } else {
      const error =
        result.interview?.last_error ||
        result.last_error ||
        result.message ||
        "The server did not confirm that the email was sent.";

      showNotice(
        `Interview saved, but invitation to ${payload.candidate_email} failed: ${error}`,
        "error"
      );
    }
  } catch (error) {
    showNotice(
      `Could not confirm invitation delivery: ${error.message}. Check the server terminal.`,
      "error"
    );
    await loadInterviews().catch(() => {});
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Save & send invitation";
    }
  }
});

async function startDashboard() {
  if (dashboardStarted) return;
  dashboardStarted = true;

  try {
    await loadInterviews();
  } catch (error) {
    const tbody = $("interviewRows");
    if (tbody) {
      tbody.innerHTML =
        `<tr><td colspan="5">Could not load interview statuses: ${escapeHtml(error.message)}</td></tr>`;
    }

    showNotice(
      "Dashboard could not load: " + error.message +
      ". The backend must also allow access to /api/interviews without admin authentication.",
      "error"
    );
  }
}

startDashboard();

setInterval(() => {
  loadInterviews().catch(() => {});
}, 10000);

document.getElementById("extractResume")?.addEventListener("click", async () => {
  const fileInput = document.getElementById("resumeFile");
  const message = document.getElementById("resumeMessage");
  const button = document.getElementById("extractResume");
  const file = fileInput?.files?.[0];

  if (!file) {
    message.textContent = "Please choose a resume file first.";
    return;
  }

  button.disabled = true;
  message.textContent = "Extracting resume details...";

  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/resume/extract", {
      method: "POST",
      body: formData
    });

    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Extraction failed.");

    const fields = {
      candidate_name: result.candidate_name,
      candidate_email: result.candidate_email,
      candidate_phone: result.candidate_phone
    };

    for (const [id, value] of Object.entries(fields)) {
      const input = document.getElementById(id);
      if (input && value) input.value = value;
    }

    message.textContent = "Extraction complete. Please review the details.";
  } catch (error) {
    message.textContent = "Error: " + error.message;
  } finally {
    button.disabled = false;
  }
});

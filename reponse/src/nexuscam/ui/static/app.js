async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function kindChip(kind) {
  return `<span class="chip">${kind}</span>`;
}

function renderButtons(el, items, onClickLabel) {
  el.innerHTML = items
    .map(
      (it, i) =>
        `<button data-i="${i}">${it.label}</button>`
    )
    .join("");
  el.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => onClickLabel(items[Number(btn.dataset.i)]));
  });
}

async function refresh() {
  const s = await fetch("/api/v1/status").then((r) => r.json());
  const sources = s.sources || [];
  const names = sources.map((x) => x.source_id).join(" · ") || "no source";
  document.getElementById("src").textContent = `${names}  ·  ${s.view_mode || "active"}  ${s.paused ? "PAUSED" : "LIVE"}`;
  document.getElementById("ble").textContent = JSON.stringify(s.ble, null, 2);
  const srcList = document.getElementById("src-list");
  srcList.innerHTML = sources
    .map(
      (x) =>
        `<button class="${x.active ? "on" : ""}" data-sid="${x.source_id}">${x.name || x.source_id}<small>${x.transport}</small></button>`
    )
    .join("");
  srcList.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await post("/api/v1/source/select?source_id=" + encodeURIComponent(btn.dataset.sid), {});
      const live = document.getElementById("live");
      live.src = "/api/v1/stream.mjpg?t=" + Date.now();
      refresh();
    });
  });
  const result = s.result || {};
  const counts = result.counts || {};
  const kinds = ["person", "vehicle", "animal", "object"]
    .filter((k) => counts[k])
    .map((k) => `${k} ${counts[k]}`)
    .join("   ");
  document.getElementById("counts").textContent = kinds || "waiting for tracks…";
  const objects = result.objects || [];
  document.getElementById("table").innerHTML = objects
    .map(
      (o) =>
        `<div class="card">${kindChip(o.kind)}<strong>#${o.track_id} ${String(o.label).toUpperCase()}</strong><br>${(o.lines || []).join("<br>")}</div>`
    )
    .join("");
}

document.querySelectorAll("button[data-src]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      await post("/api/v1/source", { backend: btn.dataset.src });
    } catch (err) {
      alert(err.message);
    }
    refresh();
  });
});

document.getElementById("open-url").addEventListener("click", async () => {
  const url = document.getElementById("url").value.trim();
  if (!url) return;
  try {
    await post("/api/v1/source", { backend: url.includes("rtsp") ? "rtsp" : "http", url });
  } catch (err) {
    alert(err.message);
  }
  refresh();
});

document.getElementById("usb-scan").addEventListener("click", async () => {
  const data = await fetch("/api/v1/cameras/usb").then((r) => r.json());
  const cams = data.cameras || [];
  renderButtons(
    document.getElementById("usb-list"),
    cams.map((c) => ({
      label: `${c.is_pc_camera ? "PC" : "USB"} ${c.index}: ${c.name} (${c.width}x${c.height})`,
      backend: c.is_pc_camera ? "pc" : `usb:${c.index}`,
    })),
    async (item) => {
      await post("/api/v1/source", { backend: item.backend });
      refresh();
    }
  );
});

document.getElementById("usb-all").addEventListener("click", async () => {
  await post("/api/v1/cameras/usb/open-all", {});
  refresh();
});

document.getElementById("open-pc").addEventListener("click", async () => {
  try {
    await post("/api/v1/cameras/pc", {});
  } catch (err) {
    alert(err.message);
  }
  refresh();
});

document.getElementById("wifi-scan").addEventListener("click", async () => {
  document.getElementById("wifi-list").textContent = "scanning LAN…";
  const data = await fetch("/api/v1/cameras/wifi").then((r) => r.json());
  const eps = data.endpoints || [];
  if (!eps.length) {
    document.getElementById("wifi-list").textContent = "no HTTP/RTSP cameras on this LAN";
    return;
  }
  renderButtons(
    document.getElementById("wifi-list"),
    eps.map((e) => ({ label: `${e.kind} ${e.url}`, url: e.url, kind: e.kind })),
    async (item) => {
      await post("/api/v1/source", { backend: item.kind === "rtsp" ? "rtsp" : "http", url: item.url });
      refresh();
    }
  );
});

document.getElementById("bt-scan").addEventListener("click", async () => {
  const data = await fetch("/api/v1/cameras/bluetooth").then((r) => r.json());
  document.getElementById("ble").textContent = JSON.stringify(data, null, 2);
});

document.getElementById("bt-attach").addEventListener("click", async () => {
  try {
    const res = await post("/api/v1/link/bluetooth/attach", {});
    if (res.detail) alert(res.detail);
  } catch (err) {
    alert(err.message);
  }
  refresh();
});

document.getElementById("view-active").addEventListener("click", async () => {
  await post("/api/v1/view", { mode: "active" });
  document.getElementById("live").src = "/api/v1/stream.mjpg?t=" + Date.now();
});

document.getElementById("view-mosaic").addEventListener("click", async () => {
  await post("/api/v1/view", { mode: "mosaic" });
  document.getElementById("live").src = "/api/v1/stream.mjpg?mosaic=true&t=" + Date.now();
});

document.querySelectorAll("input[data-ctrl]").forEach((el) => {
  el.addEventListener("change", () => post("/api/v1/control", { name: el.dataset.ctrl, value: Number(el.value) }));
});

document.querySelectorAll("button[data-ptz]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const body = { pan: 0, tilt: 0, zoom: 0 };
    body[btn.dataset.ptz] = Number(btn.dataset.val);
    post("/api/v1/ptz", body);
  });
});

document.getElementById("browser-cam").addEventListener("click", async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
  const ws = new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + "/ws/ingress/pc:browser");
  ws.binaryType = "arraybuffer";
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const video = document.createElement("video");
  video.srcObject = stream;
  video.muted = true;
  await video.play();
  const tick = () => {
    if (ws.readyState === 1 && video.videoWidth) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0);
      canvas.toBlob((blob) => {
        if (blob) blob.arrayBuffer().then((buf) => ws.send(buf));
      }, "image/jpeg", 0.75);
    }
    setTimeout(tick, 66);
  };
  tick();
});

setInterval(refresh, 600);
refresh();

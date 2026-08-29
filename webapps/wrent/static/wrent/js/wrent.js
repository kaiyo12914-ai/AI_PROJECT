// webapps/wrent/static/wrent/js/wrent.js
document.addEventListener("DOMContentLoaded", function () {
  // State
  let currentCategoryId = null;
  let currentPickupStationId = null;
  let currentReturnStationId = null;
  let metaData = { stations: [], categories: [] };

  // DOM Elements
  const tabBtns = document.querySelectorAll(".nav-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  const pickupStationSelect = document.getElementById("pickupStation");
  const returnStationSelect = document.getElementById("returnStation");
  const startTimeInput = document.getElementById("startTime");
  const endTimeInput = document.getElementById("endTime");
  const insuranceCheck = document.getElementById("hasInsurance");
  const categoryContainer = document.getElementById("categoryContainer");

  // Summary Elements
  const sumDuration = document.getElementById("sumDuration");
  const sumBaseFee = document.getElementById("sumBaseFee");
  const sumCrossFee = document.getElementById("sumCrossFee");
  const sumInsFee = document.getElementById("sumInsFee");
  const sumTotal = document.getElementById("sumTotal");
  const btnSubmitReservation = document.getElementById("btnSubmitReservation");
  const reservationMsg = document.getElementById("reservationMsg");

  // Modals
  const checkoutModal = document.getElementById("checkoutModal");
  const checkinModal = document.getElementById("checkinModal");
  const billModal = document.getElementById("billModal");

  // 1. Initialize Tabs
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.dataset.tab;
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");

      if (targetId === "pane-records") {
        loadRecords();
      }
    });
  });

  // 2. Set Default Times (start: now + 1h, end: start + 4h)
  function initDefaultTimes() {
    const now = new Date();
    now.setMinutes(0, 0, 0);
    now.setHours(now.getHours() + 1);

    const end = new Date(now.getTime() + 4 * 3600 * 1000);

    startTimeInput.value = formatDateTimeLocal(now);
    endTimeInput.value = formatDateTimeLocal(end);
  }

  function formatDateTimeLocal(d) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // 3. Load Meta Data (Stations & Categories)
  async function loadMeta() {
    try {
      const url = typeof apiurl === "function" ? apiurl("/wrent/api/meta/") : "/wrent/api/meta/";
      const res = await fetch(url);
      const result = await res.json();
      if (result.status === "ok") {
        metaData = result.data;
        renderMeta();
      }
    } catch (err) {
      console.error("載入站點資訊失敗:", err);
    }
  }

  function renderMeta() {
    // Populate Station Selects
    pickupStationSelect.innerHTML = '<option value="">-- 請選擇取車站點 --</option>';
    returnStationSelect.innerHTML = '<option value="">-- 請選擇還車站點 --</option>';

    metaData.stations.forEach((st) => {
      const opt1 = document.createElement("option");
      opt1.value = st.id;
      opt1.textContent = `${st.name} (${st.station_code})`;
      pickupStationSelect.appendChild(opt1);

      const opt2 = document.createElement("option");
      opt2.value = st.id;
      opt2.textContent = `${st.name} (${st.station_code})`;
      returnStationSelect.appendChild(opt2);
    });

    if (metaData.stations.length > 0) {
      pickupStationSelect.value = metaData.stations[0].id;
      returnStationSelect.value = metaData.stations[0].id;
      currentPickupStationId = metaData.stations[0].id;
      currentReturnStationId = metaData.stations[0].id;
    }

    // Render Categories
    categoryContainer.innerHTML = "";
    metaData.categories.forEach((cat, idx) => {
      const card = document.createElement("div");
      card.className = `category-card ${idx === 0 ? "selected" : ""}`;
      card.dataset.categoryId = cat.id;

      if (idx === 0) currentCategoryId = cat.id;

      card.innerHTML = `
        <span class="badge-tag">${cat.category_code}</span>
        <div class="category-name">${cat.name}</div>
        <div class="category-pricing">
          <div>時租：NT$ ${cat.hourly_rate} / 小時</div>
          <div>單日上限：NT$ ${cat.daily_cap_rate} / 日</div>
          <div>里程費：NT$ ${cat.mileage_rate} / 公里</div>
        </div>
      `;

      card.addEventListener("click", () => {
        document.querySelectorAll(".category-card").forEach((c) => c.classList.remove("selected"));
        card.classList.add("selected");
        currentCategoryId = cat.id;
        triggerQuote();
      });

      categoryContainer.appendChild(card);
    });

    triggerQuote();
  }

  // 4. Trigger Real-time Quote Calculation
  async function triggerQuote() {
    if (!currentCategoryId || !startTimeInput.value || !endTimeInput.value) return;

    currentPickupStationId = pickupStationSelect.value;
    currentReturnStationId = returnStationSelect.value;

    const payload = {
      category_id: currentCategoryId,
      start_time: startTimeInput.value,
      end_time: endTimeInput.value,
      pickup_station_id: currentPickupStationId,
      return_station_id: currentReturnStationId,
      has_insurance: insuranceCheck.checked,
    };

    try {
      const url = typeof apiurl === "function" ? apiurl("/wrent/api/quote/") : "/wrent/api/quote/";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (result.status === "ok") {
        const q = result.data;
        sumDuration.textContent = `${q.duration_hours} 小時 (計費 ${q.billed_hours} 小時)`;
        sumBaseFee.textContent = `NT$ ${q.base_time_fee.toFixed(2)}`;
        sumCrossFee.textContent = `NT$ ${q.cross_station_fee.toFixed(2)}`;
        sumInsFee.textContent = `NT$ ${q.insurance_fee.toFixed(2)}`;
        sumTotal.textContent = `NT$ ${q.total_estimated.toFixed(2)}`;
      } else {
        sumTotal.textContent = `試算錯誤: ${result.message}`;
      }
    } catch (err) {
      console.error("試算請求失敗:", err);
    }
  }

  // Listeners for Quote Updates
  [pickupStationSelect, returnStationSelect, startTimeInput, endTimeInput, insuranceCheck].forEach((el) => {
    el.addEventListener("change", triggerQuote);
  });

  // 5. Submit Reservation
  btnSubmitReservation.addEventListener("click", async () => {
    const userName = document.getElementById("userName").value.trim();
    const userPhone = document.getElementById("userPhone").value.trim();

    if (!userName) {
      alert("請輸入預約人姓名或帳號！");
      return;
    }
    if (!currentPickupStationId || !currentReturnStationId) {
      alert("請選擇取車與還車站點！");
      return;
    }

    const payload = {
      user_name: userName,
      user_phone: userPhone,
      category_id: currentCategoryId,
      pickup_station_id: currentPickupStationId,
      return_station_id: currentReturnStationId,
      start_time: startTimeInput.value,
      end_time: endTimeInput.value,
      has_insurance: insuranceCheck.checked,
    };

    btnSubmitReservation.disabled = true;
    reservationMsg.textContent = "處理預約排程中...";

    try {
      const url = typeof apiurl === "function" ? apiurl("/wrent/api/reservations/") : "/wrent/api/reservations/";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (result.status === "ok") {
        alert(`預約成功！單號：${result.data.reservation_no}\n指派車輛：${result.data.plate_number}`);
        reservationMsg.textContent = `預約成功！單號：${result.data.reservation_no}`;
        // 切換到紀錄頁面
        document.querySelector('[data-tab="pane-records"]').click();
      } else {
        alert(`預約失敗：${result.message}`);
        reservationMsg.textContent = `預約失敗：${result.message}`;
      }
    } catch (err) {
      alert("預約連線異常：" + err);
    } finally {
      btnSubmitReservation.disabled = false;
    }
  });

  // 6. Load Records & Render Table
  async function loadRecords() {
    const tbody = document.getElementById("recordsTableBody");
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">資料載入中...</td></tr>';

    try {
      const url = typeof apiurl === "function" ? apiurl("/wrent/api/records/") : "/wrent/api/records/";
      const res = await fetch(url);
      const result = await res.json();
      if (result.status === "ok") {
        renderRecords(result.data.records);
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:red;">載入失敗: ${err}</td></tr>`;
    }
  }

  function renderRecords(records) {
    const tbody = document.getElementById("recordsTableBody");
    if (!records || records.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">目前尚無租借紀錄</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    records.forEach((r) => {
      const tr = document.createElement("tr");

      let actionHtml = "-";
      if (r.status === "CONFIRMED") {
        actionHtml = `<button class="btn-action btn-checkout" data-id="${r.reservation_id}" data-no="${r.reservation_no}">辦理取車</button>`;
      } else if (r.status === "PICKED_UP") {
        actionHtml = `<button class="btn-action btn-checkin" data-id="${r.rental_record_id}" data-no="${r.reservation_no}">辦理還車結算</button>`;
      } else if (r.status === "COMPLETED") {
        actionHtml = `<span style="color:var(--success-color);font-weight:bold;">已結算 NT$ ${r.actual_total_amount}</span>`;
      }

      tr.innerHTML = `
        <td><strong>${r.reservation_no}</strong></td>
        <td>${r.user_name}</td>
        <td>${r.category_name} (${r.plate_number})</td>
        <td>${r.start_time} ~ <br>${r.end_time}</td>
        <td>${r.pickup_station} → ${r.return_station}</td>
        <td>NT$ ${r.estimated_cost}</td>
        <td><span class="status-badge status-${r.status}">${r.status}</span></td>
        <td>${actionHtml}</td>
      `;

      tbody.appendChild(tr);
    });

    // Bind action buttons
    document.querySelectorAll(".btn-checkout").forEach((btn) => {
      btn.addEventListener("click", () => openCheckoutModal(btn.dataset.id, btn.dataset.no));
    });
    document.querySelectorAll(".btn-checkin").forEach((btn) => {
      btn.addEventListener("click", () => openCheckinModal(btn.dataset.id, btn.dataset.no));
    });
  }

  // 7. Modal Handlers: Checkout (取車)
  let activeReservationId = null;
  function openCheckoutModal(resId, resNo) {
    activeReservationId = resId;
    document.getElementById("checkoutResNo").textContent = resNo;
    document.getElementById("checkoutMileage").value = "";
    document.getElementById("checkoutFuel").value = "100";
    document.getElementById("checkoutNotes").value = "外觀完整無明顯刮痕，胎壓正常。";
    checkoutModal.classList.add("show");
  }

  document.getElementById("btnConfirmCheckout").addEventListener("click", async () => {
    const mileage = document.getElementById("checkoutMileage").value;
    const fuel = document.getElementById("checkoutFuel").value;
    const notes = document.getElementById("checkoutNotes").value;

    const payload = {
      reservation_id: activeReservationId,
      pickup_mileage: mileage ? parseFloat(mileage) : null,
      pickup_fuel: parseInt(fuel, 10),
      notes: notes,
    };

    try {
      const url = typeof apiurl === "function" ? apiurl("/wrent/api/checkout/") : "/wrent/api/checkout/";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (result.status === "ok") {
        alert(result.message);
        checkoutModal.classList.remove("show");
        loadRecords();
      } else {
        alert("取車失敗：" + result.message);
      }
    } catch (e) {
      alert("連線失敗：" + e);
    }
  });

  // 8. Modal Handlers: Checkin (還車)
  let activeRentalRecordId = null;
  function openCheckinModal(recordId, resNo) {
    activeRentalRecordId = recordId;
    document.getElementById("checkinResNo").textContent = resNo;

    // Populate stations in checkin select
    const checkinStationSelect = document.getElementById("checkinStation");
    checkinStationSelect.innerHTML = "";
    metaData.stations.forEach((st) => {
      const opt = document.createElement("option");
      opt.value = st.id;
      opt.textContent = st.name;
      checkinStationSelect.appendChild(opt);
    });

    document.getElementById("checkinMileage").value = "";
    document.getElementById("checkinFuel").value = "100";
    document.getElementById("checkinDiscount").value = "0";
    document.getElementById("checkinNotes").value = "已確認油量電量，完成基本車況檢查。";
    checkinModal.classList.add("show");
  }

  document.getElementById("btnConfirmCheckin").addEventListener("click", async () => {
    const returnStationId = document.getElementById("checkinStation").value;
    const mileage = document.getElementById("checkinMileage").value;
    const fuel = document.getElementById("checkinFuel").value;
    const discount = document.getElementById("checkinDiscount").value;
    const notes = document.getElementById("checkinNotes").value;

    if (!mileage) {
      alert("請輸入還車實際里程！");
      return;
    }

    const payload = {
      rental_record_id: activeRentalRecordId,
      return_station_id: returnStationId,
      return_mileage: parseFloat(mileage),
      return_fuel: parseInt(fuel, 10),
      discount_amount: parseFloat(discount || 0),
      notes: notes,
    };

    try {
      const url = typeof apiurl === "function" ? apiurl("/wrent/api/checkin/") : "/wrent/api/checkin/";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (result.status === "ok") {
        checkinModal.classList.remove("show");
        showBillModal(result.data);
        loadRecords();
      } else {
        alert("還車結算失敗：" + result.message);
      }
    } catch (e) {
      alert("連線失敗：" + e);
    }
  });

  function showBillModal(bill) {
    document.getElementById("billInvoiceNo").textContent = bill.invoice_no;
    document.getElementById("billHours").textContent = `${bill.total_hours_billed} 小時`;
    document.getElementById("billDistance").textContent = `${bill.total_distance_km} 公里`;
    document.getElementById("billBase").textContent = `NT$ ${bill.base_time_fee.toFixed(2)}`;
    document.getElementById("billMileage").textContent = `NT$ ${bill.mileage_fee.toFixed(2)}`;
    document.getElementById("billOverdue").textContent = `NT$ ${bill.overdue_fee.toFixed(2)}`;
    document.getElementById("billCross").textContent = `NT$ ${bill.cross_station_fee.toFixed(2)}`;
    document.getElementById("billInsurance").textContent = `NT$ ${bill.insurance_fee.toFixed(2)}`;
    document.getElementById("billDiscount").textContent = `- NT$ ${bill.discount_amount.toFixed(2)}`;
    document.getElementById("billTotal").textContent = `NT$ ${bill.total_amount.toFixed(2)}`;
    billModal.classList.add("show");
  }

  // Close modals
  document.querySelectorAll(".btn-close-modal").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".modal-backdrop").forEach((m) => m.classList.remove("show"));
    });
  });

  // Refresh records button
  const btnRefreshRecords = document.getElementById("btnRefreshRecords");
  if (btnRefreshRecords) {
    btnRefreshRecords.addEventListener("click", loadRecords);
  }

  // Kick off
  initDefaultTimes();
  loadMeta();
});

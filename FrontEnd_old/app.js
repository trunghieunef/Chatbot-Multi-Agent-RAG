const listingGrid = document.querySelector("#listing-grid");
const quickLinksGrid = document.querySelector("#quick-links-grid");
const searchInput = document.querySelector("#search-input");
const searchButton = document.querySelector("#search-button");
const categorySelect = document.querySelector("#category-select");
const locationSelect = document.querySelector("#location-select");
const priceSelect = document.querySelector("#price-select");

const totalListingsEl = document.querySelector("#total-listings");
const totalLocationsEl = document.querySelector("#total-locations");
const avgPriceEl = document.querySelector("#avg-price");
const dataSourceEl = document.querySelector("#data-source");
const resultCountEl = document.querySelector("#result-count");
const topLocationEl = document.querySelector("#top-location");
const regionSourceEl = document.querySelector("#region-source");
const regionTotalEl = document.querySelector("#region-total");
const regionTopLocationEl = document.querySelector("#region-top-location");
const topCategoryEl = document.querySelector("#top-category");

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderListings(items) {
  if (!items.length) {
    listingGrid.innerHTML = `
      <article class="listing-card">
        <div class="listing-card__content">
          <h3 class="listing-card__title">Không tìm thấy tin đăng phù hợp</h3>
          <p class="listing-card__description">Hãy thử đổi từ khóa, khu vực hoặc mức giá để xem thêm kết quả.</p>
        </div>
      </article>
    `;
    return;
  }

  listingGrid.innerHTML = items
    .map(
      (listing) => `
        <article class="listing-card">
          <div class="listing-card__media">
            <span class="listing-card__badge">${listing.badge || "Tin nổi bật"}</span>
          </div>
          <div class="listing-card__content">
            <h3 class="listing-card__title">${listing.title || "Không có tiêu đề"}</h3>
            <div class="listing-card__price">
              <strong>${listing.price_text || "Liên hệ"}</strong>
              <span>${listing.price_per_m2_text || ""}</span>
            </div>
            <div class="listing-card__meta">
              <span>${listing.area_text || "-"}</span>
              <span>${listing.bedrooms ? `${listing.bedrooms} PN` : "-"}</span>
              <span>${listing.bathrooms ? `${listing.bathrooms} WC` : "-"}</span>
              <span>${listing.location || "-"}</span>
            </div>
            <p class="listing-card__description">${listing.description || "Chưa có mô tả."}</p>
            <div class="listing-card__footer">
              <span>${listing.contact_name || "Chưa có liên hệ"}</span>
              <span>${listing.post_date || "Mới cập nhật"}</span>
            </div>
          </div>
        </article>
      `
    )
    .join("");
}

function renderQuickLinks(items) {
  quickLinksGrid.innerHTML = items
    .map(
      (item) => `
        <a href="#" class="quick-card">
          <strong>${item.name}</strong>
          <span>${item.count} tin đang hiển thị</span>
        </a>
      `
    )
    .join("");
}

function fillSelect(select, items, label) {
  select.innerHTML = `<option value="">${label}</option>` +
    items.map((item) => `<option value="${item}">${item}</option>`).join("");
}

function buildListingUrl() {
  const params = new URLSearchParams();
  if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
  if (categorySelect.value) params.set("category", categorySelect.value);
  if (locationSelect.value) params.set("location", locationSelect.value);
  if (priceSelect.value) {
    const [min, max] = priceSelect.value.split("-");
    if (min) params.set("min_price", min);
    if (max) params.set("max_price", max);
  }
  params.set("limit", "12");
  return `/api/listings?${params.toString()}`;
}

async function loadStats() {
  const stats = await fetchJson("/api/stats");
  totalListingsEl.textContent = stats.total_listings;
  totalLocationsEl.textContent = stats.total_locations;
  avgPriceEl.textContent = stats.average_price_billion ? `${stats.average_price_billion} tỷ` : "N/A";
  dataSourceEl.textContent = stats.data_source;
  regionSourceEl.textContent = stats.data_source;
  topLocationEl.textContent = stats.top_locations[0]?.name || "-";
  regionTopLocationEl.textContent = stats.top_locations[0]?.name || "-";
  topCategoryEl.textContent = stats.quick_links[0]?.name || "-";
  renderQuickLinks((stats.quick_links || []).slice(0, 4));
  fillSelect(locationSelect, (stats.top_locations || []).map((item) => item.name), "Khu vực");
}

async function loadCategories() {
  const data = await fetchJson("/api/categories");
  fillSelect(categorySelect, data.items || [], "Loại nhà đất");
}

async function loadListings() {
  const data = await fetchJson(buildListingUrl());
  resultCountEl.textContent = data.total;
  regionTotalEl.textContent = data.total;
  renderListings(data.items || []);
}

async function initialize() {
  try {
    await Promise.all([loadStats(), loadCategories()]);
    await loadListings();
  } catch (error) {
    listingGrid.innerHTML = `
      <article class="listing-card">
        <div class="listing-card__content">
          <h3 class="listing-card__title">Không tải được dữ liệu từ backend</h3>
          <p class="listing-card__description">${error.message}</p>
        </div>
      </article>
    `;
  }
}

searchButton.addEventListener("click", loadListings);
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadListings();
  }
});
categorySelect.addEventListener("change", loadListings);
locationSelect.addEventListener("change", loadListings);
priceSelect.addEventListener("change", loadListings);

initialize();

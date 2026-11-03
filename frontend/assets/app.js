const authForm = document.querySelector("#auth-form");
const authPanel = document.querySelector("#auth-panel");
const accountSession = document.querySelector("#account-session");
const accountEmail = document.querySelector("#account-email");
const statusMessage = document.querySelector("#status");
const recipeEditor = document.querySelector("#recipe-editor");
const recipeForm = document.querySelector("#recipe-form");
const recipeStatus = document.querySelector("#recipe-status");
const recipeList = document.querySelector("#recipe-list");
const recipeCount = document.querySelector("#recipe-count");
const refreshButton = document.querySelector("#refresh");
const loadMoreButton = document.querySelector("#load-more");
const assistantForm = document.querySelector("#assistant-form");
const assistantStatus = document.querySelector("#assistant-status");
const assistantAnswer = document.querySelector("#assistant-answer");
const ingredientList = document.querySelector("#ingredient-list");

let accessToken = "";
let nextRecipesLink = null;
let totalRecipes = 0;
let loadedRecipes = 0;
let editingRecipeId = null;

function apiUrl(path) {
  const base = window.APP_CONFIG?.apiBaseUrl || window.location.origin;
  return new URL(path, `${base.replace(/\/+$/, "")}/`).toString();
}

function setStatus(message, isError = false) {
  statusMessage.textContent = message;
  statusMessage.classList.toggle("d-none", !isError || !message);
  statusMessage.classList.toggle("text-danger", isError);
}

async function apiRequest(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(!isFormData && options.body ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return null;
  if (response.headers.get("content-type")?.includes("application/json")) {
    return response.json();
  }
  return response;
}

document.querySelector("#google-login").href = apiUrl("/auth/google/login");
document.querySelector('link[rel="canonical"]').href = `${window.location.origin}/`;

function addIngredientRow(values = {}) {
  const row = document.createElement("div");
  row.className = "ingredient-row";
  row.innerHTML = `
    <div class="row g-2 align-items-end">
      <div class="col-12 col-sm-5">
        <label class="form-label">Ingredient</label>
        <input class="form-control ingredient-name" maxlength="160" placeholder="Pale malt">
      </div>
      <div class="col-6 col-sm-3">
        <label class="form-label">Type</label>
        <select class="form-select ingredient-type">
          <option>Grain</option><option>Malt</option><option>Hop</option><option>Yeast</option><option>Additive</option>
        </select>
      </div>
      <div class="col-4 col-sm-2">
        <label class="form-label">Grams</label>
        <input class="form-control ingredient-amount" type="number" min="0.1" step="0.1" placeholder="500">
      </div>
      <div class="col-2 col-sm-2">
        <button class="btn btn-outline-secondary w-100 remove-ingredient" type="button" aria-label="Remove ingredient">×</button>
      </div>
    </div>`;
  row.querySelector(".ingredient-name").value = values.name || "";
  row.querySelector(".ingredient-type").value = values.ingredient_type || "Malt";
  row.querySelector(".ingredient-amount").value = values.amount_grams || "";
  row.querySelector(".remove-ingredient").addEventListener("click", () => row.remove());
  ingredientList.append(row);
}

function collectIngredients() {
  return [...ingredientList.querySelectorAll(".ingredient-row")]
    .map((row) => ({
      name: row.querySelector(".ingredient-name").value.trim(),
      ingredient_type: row.querySelector(".ingredient-type").value,
      amount_grams: Number(row.querySelector(".ingredient-amount").value),
    }))
    .filter((ingredient) => ingredient.name && ingredient.amount_grams > 0);
}

function createRecipeCard(recipe) {
  const column = document.createElement("div");
  column.className = "col-md-6";
  const card = document.createElement("article");
  card.className = "card recipe-card shadow-sm";
  const body = document.createElement("div");
  body.className = "card-body d-flex flex-column";

  const title = document.createElement("h3");
  title.className = "h5 card-title";
  title.textContent = recipe.title;
  const style = document.createElement("span");
  style.className = "badge text-bg-warning align-self-start";
  style.textContent = recipe.style;
  const facts = document.createElement("p");
  facts.className = "small text-secondary mb-0";
  facts.textContent = `${recipe.abv}% ABV · ${recipe.ibu} IBU`;
  const description = document.createElement("p");
  description.className = "card-text";
  description.textContent = recipe.description || "A recipe ready for your brewing notes.";

  body.append(title, style, facts, description);
  if (recipe.ingredients?.length) {
    const ingredientHeading = document.createElement("h4");
    ingredientHeading.className = "h6 mt-2";
    ingredientHeading.textContent = "Ingredients";
    const ingredientItems = document.createElement("ul");
    ingredientItems.className = "small text-secondary ps-3 mb-2";
    for (const ingredient of recipe.ingredients) {
      const item = document.createElement("li");
      item.textContent = `${ingredient.name} · ${ingredient.amount_grams} g ${ingredient.ingredient_type}`;
      ingredientItems.append(item);
    }
    body.append(ingredientHeading, ingredientItems);
  }

  if (recipe.file_path) {
    const download = document.createElement("button");
    download.className = "btn btn-sm btn-outline-primary recipe-attachment align-self-start";
    download.textContent = "Download attached file";
    download.addEventListener("click", () => downloadRecipeFile(recipe.id, download));
    body.append(download);
  }

  const edit = document.createElement("button");
  edit.className = "btn btn-sm btn-outline-primary align-self-start";
  edit.textContent = "Edit recipe";
  edit.addEventListener("click", () => editRecipe(recipe));
  body.append(edit);

  const remove = document.createElement("button");
  remove.className = "btn btn-sm btn-outline-danger align-self-start mt-auto";
  remove.textContent = "Delete recipe";
  remove.addEventListener("click", async () => {
    remove.disabled = true;
    try {
      await apiRequest(`/api/recipes/${recipe.id}`, { method: "DELETE" });
      await loadRecipes({ reset: true });
    } catch (error) {
      setStatus(error.message, true);
      remove.disabled = false;
    }
  });
  body.append(remove);
  card.append(body);
  column.append(card);
  return column;
}

async function downloadRecipeFile(recipeId, button) {
  button.disabled = true;
  try {
    const response = await apiRequest(`/api/recipes/${recipeId}/file?redirect=false`);
    if (response.download_url) {
      window.location.assign(response.download_url);
      return;
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "recipe-attachment";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function showEmptyRecipes(message) {
  recipeList.replaceChildren();
  const column = document.createElement("div");
  column.className = "col-12";
  const empty = document.createElement("div");
  empty.className = "empty-state p-5 text-center";
  const icon = document.createElement("span");
  icon.className = "empty-icon";
  icon.textContent = "🍻";
  const heading = document.createElement("h3");
  heading.className = "h5 mt-3";
  heading.textContent = "Your next recipe starts here";
  const text = document.createElement("p");
  text.className = "text-secondary mb-0";
  text.textContent = message;
  empty.append(icon, heading, text);
  column.append(empty);
  recipeList.append(column);
}

async function loadRecipes({ reset = true } = {}) {
  if (!accessToken) return;
  if (reset) {
    loadedRecipes = 0;
    nextRecipesLink = "/api/recipes/?skip=0&limit=12";
    recipeList.replaceChildren();
    recipeCount.textContent = "Loading your recipes…";
  }
  refreshButton.disabled = true;
  loadMoreButton.disabled = true;
  try {
    const result = await apiRequest(nextRecipesLink);
    totalRecipes = result.total;
    for (const recipe of result.items) {
      recipeList.append(createRecipeCard(recipe));
      loadedRecipes += 1;
    }
    nextRecipesLink = result.next_link;
    recipeCount.textContent = `${loadedRecipes} of ${totalRecipes} recipe${totalRecipes === 1 ? "" : "s"} in your tenant`;
    loadMoreButton.classList.toggle("d-none", !nextRecipesLink);
    if (reset && result.items.length === 0) {
      showEmptyRecipes("No recipes yet. Add one with the form to get started.");
    }
  } catch (error) {
    recipeCount.textContent = "Recipes could not be loaded.";
    setStatus(error.message, true);
  } finally {
    refreshButton.disabled = false;
    loadMoreButton.disabled = false;
  }
}

async function loadTenantInfo() {
  if (!accessToken) return;
  try {
    const tenant = await apiRequest("/tenant/info");
    if (tenant.user_email) accountEmail.textContent = tenant.user_email;
    document.querySelector("#tenant-id").textContent = tenant.tenant_id;
  } catch (error) {
    setStatus(error.message, true);
  }
}

function enterSession(email, provider) {
  authPanel.classList.add("d-none");
  accountSession.classList.remove("d-none");
  recipeEditor.classList.remove("d-none");
  accountEmail.textContent = email || `Signed in with ${provider}`;
  setStatus("");
  refreshButton.disabled = false;
  loadTenantInfo();
  loadRecipes();
}

function resetRecipeForm() {
  editingRecipeId = null;
  recipeForm.reset();
  ingredientList.replaceChildren();
  addIngredientRow();
  document.querySelector("#recipe-editor-title").textContent = "Add a recipe";
  document.querySelector("#save-recipe").textContent = "Save recipe";
  document.querySelector("#cancel-edit").classList.add("d-none");
  recipeStatus.textContent = "";
  recipeStatus.className = "small mb-0";
}

function editRecipe(recipe) {
  editingRecipeId = recipe.id;
  recipeForm.elements.title.value = recipe.title;
  recipeForm.elements.style.value = recipe.style;
  recipeForm.elements.abv.value = recipe.abv;
  recipeForm.elements.ibu.value = recipe.ibu;
  recipeForm.elements.description.value = recipe.description || "";
  recipeForm.elements.file.value = "";
  ingredientList.replaceChildren();
  for (const ingredient of recipe.ingredients || []) {
    addIngredientRow(ingredient);
  }
  if (!recipe.ingredients?.length) addIngredientRow();
  document.querySelector("#recipe-editor-title").textContent = "Edit recipe";
  document.querySelector("#save-recipe").textContent = "Save changes";
  document.querySelector("#cancel-edit").classList.remove("d-none");
  recipeStatus.textContent = "Editing recipe. Saving keeps its current attachment unless you add a new file.";
  recipeStatus.className = "small mb-0 text-secondary";
  recipeEditor.scrollIntoView({ behavior: "smooth", block: "start" });
}

function signOut() {
  resetRecipeForm();
  accessToken = "";
  authForm.reset();
  authPanel.classList.remove("d-none");
  accountSession.classList.add("d-none");
  recipeEditor.classList.add("d-none");
  document.querySelector("#tenant-id").textContent = "Sign in to load your tenant.";
  refreshButton.disabled = true;
  loadMoreButton.classList.add("d-none");
  recipeCount.textContent = "Sign in to load your tenant's recipes.";
  showEmptyRecipes("Sign in to see your recipes or create the first one.");
}

document.querySelector("#add-ingredient").addEventListener("click", () => addIngredientRow());
document.querySelector("#cancel-edit").addEventListener("click", resetRecipeForm);
document.querySelector("#sign-out").addEventListener("click", signOut);
refreshButton.addEventListener("click", () => loadRecipes({ reset: true }));
loadMoreButton.addEventListener("click", () => loadRecipes({ reset: false }));

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(authForm);
  const action = event.submitter?.value || "login";
  const email = form.get("email");
  const password = form.get("password");
  setStatus(action === "register" ? "Creating account…" : "Signing in…");
  try {
    if (action === "register") {
      const registration = await fetch(apiUrl("/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!registration.ok) {
        const body = await registration.json().catch(() => ({}));
        throw new Error(body.detail || `Registration failed (${registration.status})`);
      }
    }
    const response = await fetch(apiUrl("/login"), {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || `Login failed (${response.status})`);
    }
    accessToken = (await response.json()).access_token;
    enterSession(email, "email");
  } catch (error) {
    setStatus(error.message, true);
  }
});

recipeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(recipeForm);
  const saveButton = document.querySelector("#save-recipe");
  const isEditing = editingRecipeId !== null;
  const file = data.get("file");
  if (file instanceof File && file.size > 8 * 1024 * 1024) {
    recipeStatus.textContent = "Choose a file smaller than 8 MB.";
    recipeStatus.className = "small mb-0 text-danger";
    return;
  }
  saveButton.disabled = true;
  recipeStatus.textContent = "Saving recipe…";
  recipeStatus.className = "small mb-0 text-secondary";
  try {
    const recipe = await apiRequest(
      isEditing ? `/api/recipes/${editingRecipeId}` : "/api/recipes/",
      {
        method: isEditing ? "PUT" : "POST",
        body: JSON.stringify({
          title: data.get("title"),
          style: data.get("style"),
          abv: Number(data.get("abv")),
          ibu: Number(data.get("ibu")),
          description: data.get("description") || null,
          ingredients: collectIngredients(),
        }),
      },
    );
    if (file instanceof File && file.size > 0) {
      const upload = new FormData();
      upload.append("file", file);
      await apiRequest(`/api/recipes/${recipe.id}/file`, {
        method: "POST",
        body: upload,
      });
    }
    resetRecipeForm();
    recipeStatus.textContent = isEditing
      ? "Recipe changes saved."
      : "Recipe saved to your tenant.";
    recipeStatus.className = "small mb-0 text-success";
    await loadRecipes({ reset: true });
  } catch (error) {
    recipeStatus.textContent = error.message;
    recipeStatus.className = "small mb-0 text-danger";
    await loadRecipes({ reset: true });
  } finally {
    saveButton.disabled = false;
  }
});

assistantForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  assistantAnswer.textContent = "";
  if (!accessToken) {
    assistantStatus.textContent = "Sign in first so the assistant can check your tenant's feature flag.";
    assistantStatus.className = "small text-warning mt-2 mb-0";
    return;
  }
  if (!window.APP_CONFIG?.aiAssistantConfigured) {
    assistantStatus.textContent = "The Gemini API key is not configured for this deployment.";
    assistantStatus.className = "small text-warning mt-2 mb-0";
    return;
  }
  const askButton = document.querySelector("#ask-assistant");
  askButton.disabled = true;
  assistantStatus.textContent = "Connecting to Gemini…";
  assistantStatus.className = "small text-light-emphasis mt-2 mb-0";
  try {
    const response = await fetch(apiUrl("/api/assistant/stream"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ prompt: document.querySelector("#prompt").value }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Assistant failed (${response.status})`);
    }
    assistantStatus.textContent = "Streaming answer…";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value || new Uint8Array(), { stream: !done });
      const events = pending.split("\n\n");
      pending = events.pop() || "";
      for (const eventText of events) {
        const eventName = eventText.split("\n").find((line) => line.startsWith("event: "))?.slice(7);
        const data = eventText.split("\n").find((line) => line.startsWith("data: "));
        if (!data) continue;
        const payload = JSON.parse(data.slice(6));
        if (eventName === "progress" && payload.message) {
          assistantStatus.textContent = payload.message;
        }
        if (payload.text) assistantAnswer.textContent += payload.text;
        if (payload.error) throw new Error(payload.error);
      }
      if (done) break;
    }
    assistantStatus.textContent = assistantAnswer.textContent
      ? "Answer complete."
      : "The assistant returned an empty answer. Please try again.";
  } catch (error) {
    assistantStatus.textContent = error.message;
    assistantStatus.className = "small text-danger mt-2 mb-0";
  } finally {
    askButton.disabled = false;
  }
});

document.querySelector("#recipe-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file && file.size > 8 * 1024 * 1024) {
    event.target.value = "";
    recipeStatus.textContent = "Choose a file smaller than 8 MB.";
    recipeStatus.className = "small mb-0 text-danger";
  } else if (file) {
    recipeStatus.textContent = `${file.name} selected`;
    recipeStatus.className = "small mb-0 text-secondary";
  }
});

const tokenFromCallback = new URLSearchParams(window.location.hash.slice(1)).get("access_token");
if (tokenFromCallback) {
  accessToken = tokenFromCallback;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  enterSession("", "Google");
}

const measurementId = window.APP_CONFIG?.googleAnalyticsId;
const consentBanner = document.querySelector("#analytics-consent");
function enableAnalytics() {
  if (!measurementId || !/^G-[A-Z0-9]+$/.test(measurementId)) return;
  const analyticsScript = document.createElement("script");
  analyticsScript.async = true;
  analyticsScript.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.append(analyticsScript);
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", measurementId);
}

if (measurementId && !localStorage.getItem("akatosh-analytics-consent")) {
  consentBanner.hidden = false;
}
document.querySelector("#analytics-accept").addEventListener("click", () => {
  localStorage.setItem("akatosh-analytics-consent", "accepted");
  consentBanner.hidden = true;
  enableAnalytics();
});
document.querySelector("#analytics-decline").addEventListener("click", () => {
  localStorage.setItem("akatosh-analytics-consent", "declined");
  consentBanner.hidden = true;
});
if (localStorage.getItem("akatosh-analytics-consent") === "accepted") {
  enableAnalytics();
}

addIngredientRow();

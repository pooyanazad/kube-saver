// Give the theme's mobile drawer label keyboard access and an accessible name.
// Native label clicks still control the theme's existing checkbox and drawer.
function enhanceNavigation() {
  const menu = document.querySelector('header label[for="__drawer"]');
  const drawer = document.getElementById("__drawer");
  const navigation = document.querySelector('nav[aria-label="Navigation"]');
  if (!menu || !drawer || !navigation) return;
  navigation.id ||= "primary-navigation";
  menu.setAttribute("role", "button");
  menu.setAttribute("tabindex", "0");
  menu.setAttribute("aria-controls", navigation.id);
  const update = () => {
    menu.setAttribute("aria-expanded", String(drawer.checked));
    menu.setAttribute("aria-label", drawer.checked ? "Close navigation" : "Open navigation");
  };
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      // Material also activates labels on Enter at the window level.
      // Stop propagation so a single key press cannot toggle twice.
      event.stopPropagation();
      menu.click();
    }
  });
  drawer.addEventListener("change", update);
  update();
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", enhanceNavigation, { once: true });
} else {
  enhanceNavigation();
}

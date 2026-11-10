// Mobile menu toggle for the Epi navigation block (replaces WordPress's interactivity script).
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".wp-block-navigation").forEach((nav) => {
    const container = nav.querySelector(".wp-block-navigation__responsive-container");
    const open = nav.querySelector(".wp-block-navigation__responsive-container-open");
    const close = nav.querySelector(".wp-block-navigation__responsive-container-close");
    if (!container || !open || !close) return;
    const dialog = container.querySelector(".wp-block-navigation__responsive-dialog");
    const set = (isOpen) => {
      container.classList.toggle("is-menu-open", isOpen);
      container.classList.toggle("has-modal-open", isOpen);
      document.documentElement.classList.toggle("has-modal-open", isOpen);
      if (dialog) {
        dialog.toggleAttribute("aria-modal", isOpen);
        if (isOpen) dialog.setAttribute("role", "dialog"); else dialog.removeAttribute("role");
      }
      (isOpen ? close : open).focus();
    };
    open.addEventListener("click", () => set(true));
    close.addEventListener("click", () => set(false));
    container.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
  });
});

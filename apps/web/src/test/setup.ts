import "@testing-library/jest-dom/vitest";

// jsdom has dialog elements but does not implement the browser's modal methods.
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
};

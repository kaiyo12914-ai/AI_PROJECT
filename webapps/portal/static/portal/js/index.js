(() => {
  const cards = document.querySelectorAll(".svg-card");
  cards.forEach((card) => {
    card.addEventListener("keydown", (event) => {
      if (event.code === "Space" || event.key === " ") {
        event.preventDefault();
        card.click();
      }
    });
  });
})();

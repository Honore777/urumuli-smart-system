// Simple word-swap + subtle appearance animation for landing page
(function(){
  const words = [
    "gucunga imari",
    "kugenzura stocks",
    "gucunga kwishyura",
    "raporo z'ubucuruzi"
  ];

  const el = document.getElementById('swap-word');
  if (!el) return;

  let idx = 0;
  function swap(){
    // fade out
    el.classList.remove('opacity-100');
    el.classList.add('opacity-0');

    setTimeout(()=>{
      idx = (idx + 1) % words.length;
      el.textContent = words[idx];
      // fade in
      el.classList.remove('opacity-0');
      el.classList.add('opacity-100');
    }, 500);
  }

  // start after small delay, then swap every 2500ms
  setTimeout(()=>{
    setInterval(swap, 2500);
  }, 800);

})();

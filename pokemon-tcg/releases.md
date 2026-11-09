---
layout: page
title: Pokémon TCG Release Tracker
permalink: /pokemon-tcg/releases/
---
<nav aria-label="Side Quest Dispatch sections" style="display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0 1.5rem;">
  <a href="{{ '/' | relative_url }}">Home</a>
  <a href="{{ '/pokemon-tcg/releases/' | relative_url }}">🎴 Pokémon TCG Releases</a>
</nav>
<p>US English-language products. Release dates come from Pokémon's official announcements. Prices labeled <strong>third-party</strong> are reference prices from Celadon Info, not independently confirmed manufacturer MSRP. Unknown prices are shown as unverified. This page is a reviewed snapshot, not a live stock feed.</p>
<p><label for="tcg-search">Search products:</label> <input id="tcg-search" type="search" placeholder="Product name"></p>
<p><label for="tcg-filter">Release window:</label> <select id="tcg-filter"><option value="all">All</option><option value="released">Released</option><option value="upcoming">Upcoming</option></select></p>
<table><thead><tr><th>Release date</th><th>Product</th><th>US price reference</th><th>Source</th></tr></thead><tbody id="tcg-products">
{% assign products = site.data.pokemon_tcg_releases.products | sort: "date" %}
{% for product in products %}
<tr data-name="{{ product.name | downcase | escape }}" data-date="{{ product.date }}">
<td>{{ product.date }}</td><td>{{ product.name | escape }}</td>
<td>{% if product.msrp_usd %}${{ product.msrp_usd }} ({{ product.price_verification }}){% else %}Not verified{% endif %}</td>
<td><a href="{{ product.source }}" rel="noopener noreferrer">Pokémon announcement</a>{% if product.price_source %} · <a href="{{ product.price_source }}" rel="noopener noreferrer">Price reference</a>{% endif %}</td>
</tr>
{% endfor %}
</tbody></table>
<p>Last verified: {{ site.data.pokemon_tcg_releases.last_verified }}. Dates with only a month are not confirmed to a specific day.</p>
<script>
(function () {
  const search = document.getElementById('tcg-search');
  const filter = document.getElementById('tcg-filter');
  const rows = Array.from(document.querySelectorAll('#tcg-products tr'));
  function update() {
    const today = new Date().toISOString().slice(0,10);
    const term = search.value.toLowerCase().trim();
    rows.forEach(row => {
      const date = row.dataset.date;
      const released = date.length === 10 && date <= today;
      const upcoming = date.length !== 10 || date > today;
      row.hidden = !row.dataset.name.includes(term) ||
        (filter.value === 'released' && !released) ||
        (filter.value === 'upcoming' && !upcoming);
    });
  }
  search.addEventListener('input', update);
  filter.addEventListener('change', update);
  update();
})();
</script>

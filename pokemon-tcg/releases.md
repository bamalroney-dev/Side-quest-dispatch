---
layout: page
title: Pokémon TCG Release Tracker
permalink: /pokemon-tcg/releases/
---
<p>US English-language products. Each row links to its release-date source. Third-party reference prices may differ from what retailers charge.</p>
<p><label for="tcg-search">Search products:</label> <input id="tcg-search" type="search" placeholder="Product name"></p>
<p><label for="tcg-filter">Release window:</label> <select id="tcg-filter"><option value="all">All</option><option value="released">Released</option><option value="upcoming">Upcoming</option></select></p>
<table><thead><tr><th>Release date</th><th>Product</th><th>Manufacturer MSRP</th><th>Third-party reference</th><th>Source</th></tr></thead><tbody id="tcg-products">
{% assign products = site.data.pokemon_tcg_releases.products | sort: "date" %}
{% for product in products %}
<tr data-name="{{ product.name | downcase | escape }}" data-date="{{ product.date }}">
<td>{{ product.date }}</td><td>{{ product.name | escape }}</td>
<td>{% if product.msrp_verified and product.msrp_usd %}${{ product.msrp_usd }}{% else %}MSRP not verified{% endif %}</td><td>{% if product.reference_price_usd %}${{ product.reference_price_usd }} (third-party){% else %}—{% endif %}</td>
<td><a href="{{ product.source | escape }}" rel="noopener noreferrer">{{ product.source_label | default: "Pokémon announcement" | escape }}</a>{% if product.reference_price_source %} · <a href="{{ product.reference_price_source | escape }}" rel="noopener noreferrer">Price reference</a>{% endif %}</td>
</tr>
{% endfor %}
</tbody></table>
<p>Tracker updated {{ site.data.pokemon_tcg_releases.last_verified }}. Dates with only a month indicate that the day is still pending.</p>
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

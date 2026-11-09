import React from 'react';
import SchoolMap from './components/SchoolMap';

// Straight into the map: / shows all six schools, /wagner (or any school's slug) opens with that one.
const SLUGS = ['wagner', 'blankenburg', 'robeson', 'pennypacker', 'fitler', 'amynw'];
const slug = window.location.pathname.replace(/^\/+|\/+$/g, '').toLowerCase();

export default function App() {
  return <SchoolMap initialSlug={SLUGS.includes(slug) ? slug : null} />;
}

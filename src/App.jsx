import React, { useEffect, useState } from 'react';
import Landing from './components/Landing';
import SchoolMap from './components/SchoolMap';

const SLUGS = ['wagner', 'blankenburg'];
const route = () => {
  const p = window.location.pathname.replace(/^\/+|\/+$/g, '').toLowerCase();
  return SLUGS.includes(p) ? p : null;
};

export default function App() {
  const [slug, setSlug] = useState(route);
  useEffect(() => {
    const onPop = () => setSlug(route());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const go = (s) => {
    window.history.pushState(null, '', s ? `/${s}` : '/');
    setSlug(s);
  };
  return slug ? <SchoolMap key={slug} slug={slug} onSchool={go} onHome={() => go(null)} /> : <Landing onOpen={go} />;
}

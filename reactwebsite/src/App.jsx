import { useState, useEffect, useRef } from "react";

// ============================================================
// TRANSLATIONS - FR default (index 0), EN (index 1)
// ============================================================
const T = {
  nav: {
    home:       ["Accueil",               "Home"],
    features:   ["Fonctionnalités",       "Features"],
    solutions:  ["Solutions",             "Solutions"],
    pricing:    ["Tarifs",                "Pricing"],
    howItWorks: ["Comment ça marche",     "How It Works"],
    about:      ["À propos",              "About"],
    contact:    ["Contact",               "Contact"],
    demo:       ["Démo Gratuite",         "Free Demo"],
  },
  hero: {
    badge: ["Plateforme de Gestion des Membres", "Membership Management Platform"],
    title1: ["Gérez vos membres.",        "Manage your members."],
    title2: ["Fidélisez. Automatisez.",   "Retain. Automate."],
    title3: ["Développez.",               "Grow."],
    sub: [
      "MemberSync est la plateforme numérique tout-en-un développée par NextSolutions pour fidéliser vos clients, encaisser des prépaiements et gérer vos membres automatiquement.",
      "MemberSync is the all-in-one digital platform by NextSolutions to retain customers, collect prepayments and manage members automatically.",
    ],
    cta1: ["Demander une Démo",   "Request a Demo"],
    cta2: ["Voir nos tarifs",     "See Pricing"],
  },
  stats: {
    s1: ["Établissements partenaires", "Partner Establishments"],
    s2: ["Membres actifs",             "Active Members"],
    s3: ["Pays en Afrique",            "Countries in Africa"],
    s4: ["Satisfaction client",        "Customer Satisfaction"],
  },
  problem: {
    tag:    ["Le Problème",    "The Problem"],
    title:  ["Pourquoi vos clients ne reviennent pas ?", "Why don't your clients come back?"],
    p1t: ["Pas de suivi client",           "No customer follow-up"],
    p1d: ["Vous perdez des clients faute d'un système de fidélisation structuré.", "You lose clients without a structured loyalty system."],
    p2t: ["Gestion manuelle fastidieuse",  "Tedious manual management"],
    p2d: ["Cahiers, feuilles volantes, Excel : des erreurs et une perte de temps garanties.", "Notebooks, loose papers, Excel: guaranteed errors and time wasted."],
    p3t: ["Aucune visibilité sur vos revenus", "No visibility on your revenue"],
    p3d: ["Sans dashboard, impossible de savoir combien vous rapportent vraiment vos membres.", "Without a dashboard, impossible to know how much your members actually bring in."],
    solTitle: ["MemberSync, la solution intelligente", "MemberSync, the smart solution"],
    solDesc:  ["Une plateforme numérique tout-en-un pour transformer votre business et fidéliser durablement vos clients.", "An all-in-one digital platform to transform your business and durably retain your customers."],
    check1: ["Carte membre numérique avec QR Code",    "Digital member card with QR Code"],
    check2: ["Prépaiements et abonnements automatisés","Automated prepayments and subscriptions"],
    check3: ["Dashboard en temps réel",                "Real-time dashboard"],
    check4: ["Notifications et rappels automatiques",  "Automatic notifications and reminders"],
  },
  features: {
    tag:   ["Fonctionnalités",          "Features"],
    title: ["Tout ce dont vous avez besoin", "Everything you need"],
    sub:   ["MemberSync centralise la gestion de vos membres dans une plateforme puissante et intuitive.", "MemberSync centralizes member management in a powerful, intuitive platform."],
    f: [
      { icon:"💳", t:["Carte Membre Numérique","Digital Member Card"], d:["Émettez des cartes membres numériques avec QR Code scannable pour une identification instantanée.","Issue digital member cards with scannable QR Code for instant identification."] },
      { icon:"💰", t:["Prépaiement et Abonnements","Prepayment and Subscriptions"], d:["Encaissez des prépaiements et gérez des forfaits automatiquement pour sécuriser vos revenus.","Collect prepayments and manage packages automatically to secure your revenue."] },
      { icon:"📊", t:["Dashboard Analytique","Analytics Dashboard"], d:["Visualisez en temps réel les visites, revenus, et l'activité de vos membres.","Visualize visits, revenue, and member activity in real time."] },
      { icon:"🔔", t:["Notifications Automatiques","Automatic Notifications"], d:["Rappels de renouvellement, anniversaires, offres spéciales tout se fait automatiquement.","Renewal reminders, birthdays, special offers everything happens automatically."] },
      { icon:"🎯", t:["Programme de Fidélité","Loyalty Program"], d:["Récompensez vos membres fidèles avec des points, des réductions et des avantages exclusifs.","Reward loyal members with points, discounts and exclusive perks."] },
      { icon:"📱", t:["Application Mobile","Mobile Application"], d:["Gérez votre business depuis votre smartphone, où que vous soyez.","Manage your business from your smartphone, wherever you are."] },
    ],
  },
  solutions: {
    tag:   ["Solutions",                      "Solutions"],
    title: ["Pour chaque secteur d'activité", "For every industry"],
    sub:   ["MemberSync s'adapte à tous les types d'organisations à travers l'Afrique et le monde.", "MemberSync adapts to all types of organizations across Africa and the world."],
    sectors: [
      { icon:"✂️", t:["Salons de Coiffure","Hair Salons"], d:["Fidélisez vos clients, gérez les abonnements et récompensez la fidélité.","Retain clients, manage subscriptions and reward loyalty."] },
      { icon:"🏋️", t:["Salles de Sport","Gyms and Fitness"], d:["Suivi des membres, gestion des accès et abonnements mensuels simplifiés.","Member tracking, access management and simplified monthly subscriptions."] },
      { icon:"✈️", t:["Agences de Voyage","Travel Agencies"], d:["Programmes fidélité et gestion de clientèle pour agences.","Loyalty programs and customer management for agencies."] },
      { icon:"🏫", t:["Écoles et Académies","Schools and Academies"], d:["Gestion des inscriptions, paiements et suivi des élèves.","Registration management, payments and student tracking."] },
      { icon:"🤝", t:["Associations","Associations"], d:["Cotisations automatisées et gestion de communauté simplifiée.","Automated dues and simplified community management."] },
      { icon:"🏪", t:["Commerces et Boutiques","Shops and Stores"], d:["Programmes de fidélité et gestion des clients VIP.","Loyalty programs and VIP customer management."] },
    ],
  },
  howItWorks: {
    tag:   ["Comment ça marche", "How It Works"],
    title: ["3 étapes pour démarrer", "3 steps to get started"],
    steps: [
      { n:"01", t:["Inscrivez votre établissement","Register your establishment"], d:["Créez votre compte MemberSync en quelques minutes et configurez votre profil.","Create your MemberSync account in minutes and set up your profile."] },
      { n:"02", t:["Inscrivez vos membres","Enroll your members"], d:["Ajoutez vos clients, émettez leurs cartes numériques et paramétrez leurs avantages.","Add your customers, issue their digital cards and set up their benefits."] },
      { n:"03", t:["Gérez et développez","Manage and grow"], d:["Suivez l'activité en temps réel, automatisez les rappels et fidélisez durablement.","Track activity in real time, automate reminders and build lasting loyalty."] },
    ],
  },
  pricing: {
    tag:   ["Tarifs",                          "Pricing"],
    title: ["Des tarifs simples et transparents", "Simple, transparent pricing"],
    sub:   ["Choisissez la formule adaptée à votre établissement. Sans surprise, sans frais cachés.", "Choose the plan that fits your establishment. No surprises, no hidden fees."],
    plans: [
      {
        icon:"🌱", name:["Starter","Starter"], desc:["Idéal pour démarrer","Ideal to get started"],
        price:["Sur devis","On quote"],
        features:[["Jusqu'à 100 membres","Up to 100 members"],["Cartes membres numériques","Digital member cards"],["Dashboard basique","Basic dashboard"],["Support WhatsApp","WhatsApp support"]],
        cta:["Nous contacter","Contact Us"], ctaStyle:"outline",
      },
      {
        icon:"🚀", name:["Business","Business"], desc:["Le plus populaire","Most popular"],
        price:["Sur devis","On quote"], popular:true,
        features:[["Membres illimités","Unlimited members"],["Prépaiements et abonnements","Prepayments and subscriptions"],["Dashboard analytique complet","Full analytics dashboard"],["Notifications automatiques","Automatic notifications"],["Programme de fidélité","Loyalty program"],["Support prioritaire","Priority support"]],
        cta:["Nous contacter","Contact Us"], ctaStyle:"accent",
      },
      {
        icon:"🏢", name:["Enterprise","Enterprise"], desc:["Multi-établissements","Multi-location"],
        price:["Sur devis","On quote"],
        features:[["Tout Business inclus","Everything in Business"],["Multi-établissements","Multi-location"],["API et intégrations","API and integrations"],["Rapport personnalisé","Custom reporting"],["Manager dédié","Dedicated manager"],["Formation sur site","On-site training"]],
        cta:["Nous contacter","Contact Us"], ctaStyle:"gold",
      },
    ],
    note:["Tous les tarifs sont personnalisés selon votre taille et vos besoins. Contactez-nous pour un devis gratuit.","All pricing is customized based on your size and needs. Contact us for a free quote."],
  },
  testimonials: {
    tag:   ["Témoignages",            "Testimonials"],
    title: ["Ce que disent nos clients", "What our clients say"],
    reviews: [
      { name:"Don William Barbershop", role:["Salon de coiffure, Yaoundé","Barbershop, Yaoundé"], avatar:"✂️", text:["Depuis MemberSync, nos clients reviennent régulièrement. La carte membre QR a transformé notre accueil et notre chiffre d'affaires a augmenté de 40%.","Since MemberSync, our clients come back regularly. The QR member card transformed our reception and revenue increased by 40%."] },
      { name:"FitZone Gym", role:["Salle de sport, Douala","Gym, Douala"], avatar:"🏋️", text:["La gestion des abonnements est devenue un jeu d'enfant. Plus de papier, tout est numérique et automatique.","Subscription management has become child's play. No more paper, everything is digital and automatic."] },
      { name:"Studio Beauté Elite", role:["Institut de beauté, Abidjan","Beauty salon, Abidjan"], avatar:"💅", text:["Le programme de fidélité a augmenté notre chiffre d'affaires de 30% en 3 mois. Incroyable outil pour fidéliser.","The loyalty program increased our revenue by 30% in 3 months. Incredible tool for customer retention."] },
      { name:"Académie Lumière", role:["École, Dakar","School, Dakar"], avatar:"🏫", text:["Gérer 500 élèves était un cauchemar. MemberSync a simplifié tous nos processus administratifs en un seul outil.","Managing 500 students was a nightmare. MemberSync simplified all our administrative processes in one tool."] },
    ],
  },
  about: {
    tag:   ["À propos",                                   "About"],
    title: ["NextSolutions, créateur de MemberSync",      "NextSolutions, creator of MemberSync"],
    desc:  ["NextSolutions est une entreprise technologique africaine dédiée à l'accélération de la digitalisation des organisations sur le continent. Notre mission : rendre la gestion des membres simple, intelligente et accessible pour chaque entreprise, association et organisation.", "NextSolutions is an African technology company dedicated to accelerating the digitalization of organizations across the continent. Our mission: make member management simple, intelligent and accessible for every business, association and organization."],
    mission: ["Accélérer la digitalisation des entreprises africaines en offrant un système de gestion des membres fiable, moderne et automatisé.", "Accelerate the digitalization of African businesses by offering a reliable, modern and automated member management system."],
    vision:  ["Rendre la gestion des membres simple, intelligente et accessible, afin d'augmenter la performance des organisations au Cameroun et en Afrique.", "Make member management simple, intelligent and accessible, to increase organizational performance in Cameroon and Africa."],
  },
  contact: {
    tag:   ["Contact",         "Contact"],
    title: ["Parlons de votre projet", "Let's talk about your project"],
    sub:   ["Notre équipe est disponible pour vous accompagner dans la mise en place de MemberSync pour votre établissement.", "Our team is available to support you in setting up MemberSync for your establishment."],
    wa:    ["Nous contacter sur WhatsApp", "Contact us on WhatsApp"],
    email: ["Envoyer un email",            "Send an email"],
    demo:  ["Accéder à MemberSync",        "Access MemberSync"],
  },
  footer: {
    desc:    ["MemberSync est la plateforme de gestion des membres développée par NextSolutions pour les organisations africaines et mondiales.", "MemberSync is the member management platform developed by NextSolutions for African and global organizations."],
    product: ["Produit",    "Product"],
    company: ["Entreprise", "Company"],
    support: ["Support",    "Support"],
    rights:  ["Tous droits réservés.", "All rights reserved."],
    powered: ["Une solution de",       "A solution by"],
  },
};

const tr = (key, lang) => key[lang];

// ============================================================
// NS LOGO SVG — matches the uploaded logo exactly
// ============================================================
function NSLogo({ size = 44 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M 20 50 A 30 30 0 1 1 50 80" stroke="#1e2a6e" strokeWidth="8" fill="none" strokeLinecap="round"/>
      <path d="M 50 20 A 30 30 0 0 1 80 50" stroke="#E8192C" strokeWidth="7" fill="none" strokeLinecap="round"/>
      <polygon points="80,43 87,52 73,54" fill="#E8192C"/>
      <text x="50" y="58" textAnchor="middle" fontFamily="Arial Black, sans-serif" fontWeight="900" fontSize="27" fill="#1e2a6e" letterSpacing="-1">NS</text>
    </svg>
  );
}

// ============================================================
// FLAT WORLD MAP — Africa + USA + Europe with animated connections
// Works perfectly on mobile too
// ============================================================
function WorldMap() {
  const canvasRef = useRef(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let animId;
    let tick = 0;

    // City positions as [x%, y%] on a 100x100 grid (equirectangular)
    const CITIES = {
      yaounde:       [52.5, 56],
      douala:        [51.5, 56.5],
      lagos:         [50,   53],
      abidjan:       [47,   54],
      dakar:         [43,   49],
      nairobi:       [57,   57],
      johannesburg:  [55,   68],
      casablanca:    [49,   39],
      cairo:         [56,   41],
      paris:         [50,   28],
      london:        [49,   24],
      madrid:        [47,   31],
      newYork:       [22,   32],
      miami:         [21,   40],
      losAngeles:    [12,   36],
    };

    const AFRICA_CITIES = ["yaounde","douala","lagos","abidjan","dakar","nairobi","johannesburg","casablanca","cairo"];

    const CONNECTIONS = [
      ["yaounde","paris"],["lagos","london"],["dakar","newYork"],
      ["cairo","paris"],["nairobi","london"],["abidjan","madrid"],
      ["newYork","london"],["miami","paris"],["losAngeles","london"],
      ["johannesburg","london"],["casablanca","madrid"],["douala","newYork"],
    ];

    // Simplified continent polygons [x%, y%]
    const CONTINENTS = {
      africa: [[47,38],[50,36],[53,36],[56,38],[58,41],[59,45],[59,50],[58,54],[57,57],[56,61],[54,67],[53,70],[51,70],[50,67],[49,63],[48,59],[47,55],[46,51],[45,47],[44,44],[45,41],[46,39],[47,38]],
      europe: [[47,19],[50,17],[53,17],[56,18],[57,21],[57,24],[55,26],[52,27],[50,28],[48,28],[47,26],[46,23],[47,19]],
      northAmerica: [[11,15],[16,14],[21,15],[26,17],[28,20],[27,25],[25,29],[23,33],[21,37],[19,41],[17,44],[14,43],[12,39],[10,32],[10,23],[11,15]],
      southAmerica: [[22,44],[26,43],[30,45],[31,49],[30,54],[28,58],[25,63],[22,68],[20,72],[19,69],[18,64],[19,57],[20,51],[22,44]],
      asia: [[58,19],[63,16],[70,15],[77,17],[81,21],[82,26],[80,31],[77,35],[72,40],[67,38],[62,35],[59,30],[57,24],[58,19]],
      australia: [[74,62],[78,60],[82,62],[84,66],[82,70],[78,72],[74,70],[72,66],[74,62]],
    };

    const draw = () => {
      const W = canvas.width;
      const H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      // Background
      const bg = ctx.createLinearGradient(0, 0, W, H);
      bg.addColorStop(0, "#060d20");
      bg.addColorStop(1, "#0c1e44");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // Grid
      ctx.strokeStyle = "rgba(39,118,234,0.07)";
      ctx.lineWidth = 0.5;
      for (let i = 0; i <= 12; i++) { ctx.beginPath(); ctx.moveTo(i*W/12,0); ctx.lineTo(i*W/12,H); ctx.stroke(); }
      for (let i = 0; i <= 8; i++)  { ctx.beginPath(); ctx.moveTo(0,i*H/8); ctx.lineTo(W,i*H/8); ctx.stroke(); }

      // Draw continents
      const drawContinent = (pts, stroke, fill) => {
        ctx.beginPath();
        ctx.moveTo(pts[0][0]*W/100, pts[0][1]*H/100);
        pts.forEach(p => ctx.lineTo(p[0]*W/100, p[1]*H/100));
        ctx.closePath();
        ctx.fillStyle = fill; ctx.fill();
        ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke();
      };

      drawContinent(CONTINENTS.northAmerica, "rgba(39,118,234,0.55)", "rgba(39,118,234,0.1)");
      drawContinent(CONTINENTS.southAmerica, "rgba(39,118,234,0.45)", "rgba(39,118,234,0.07)");
      drawContinent(CONTINENTS.europe,       "rgba(39,118,234,0.6)",  "rgba(39,118,234,0.12)");
      drawContinent(CONTINENTS.africa,       "rgba(244,185,66,0.9)",  "rgba(244,185,66,0.18)");
      drawContinent(CONTINENTS.asia,         "rgba(39,118,234,0.35)", "rgba(39,118,234,0.06)");
      drawContinent(CONTINENTS.australia,    "rgba(39,118,234,0.3)",  "rgba(39,118,234,0.05)");

      // Connection lines + animated dots
      CONNECTIONS.forEach(([c1, c2], idx) => {
        const p1 = CITIES[c1], p2 = CITIES[c2];
        if (!p1 || !p2) return;
        const x1=p1[0]*W/100, y1=p1[1]*H/100;
        const x2=p2[0]*W/100, y2=p2[1]*H/100;
        const ctrlX = (x1+x2)/2;
        const ctrlY = Math.min(y1,y2) - Math.abs(x2-x1)*0.28;

        // Static faint line
        ctx.beginPath();
        ctx.moveTo(x1,y1);
        ctx.quadraticCurveTo(ctrlX, ctrlY, x2, y2);
        ctx.strokeStyle = "rgba(39,118,234,0.18)";
        ctx.lineWidth = 0.8;
        ctx.stroke();

        // Animated travelling dot
        const speed = 0.0012 + idx*0.00011;
        const prog = ((tick * speed + idx * 0.15) % 1);
        const bt = prog;
        const bx = (1-bt)*(1-bt)*x1 + 2*(1-bt)*bt*ctrlX + bt*bt*x2;
        const by = (1-bt)*(1-bt)*y1 + 2*(1-bt)*bt*ctrlY + bt*bt*y2;

        const grd = ctx.createRadialGradient(bx, by, 0, bx, by, 5);
        grd.addColorStop(0, "rgba(244,185,66,1)");
        grd.addColorStop(1, "rgba(244,185,66,0)");
        ctx.beginPath(); ctx.arc(bx, by, 5, 0, Math.PI*2);
        ctx.fillStyle = grd; ctx.fill();
        ctx.beginPath(); ctx.arc(bx, by, 2, 0, Math.PI*2);
        ctx.fillStyle = "#F4B942"; ctx.fill();
      });

      // City dots
      Object.entries(CITIES).forEach(([name, [px,py]]) => {
        const x=px*W/100, y=py*H/100;
        const isAfrica = AFRICA_CITIES.includes(name);
        const pulse = (Math.sin(tick*0.05 + px) + 1) / 2;
        const color = isAfrica ? "#F4B942" : "#2776EA";
        ctx.beginPath(); ctx.arc(x, y, 3+pulse*3, 0, Math.PI*2);
        ctx.fillStyle = isAfrica ? `rgba(244,185,66,${0.08+pulse*0.12})` : `rgba(39,118,234,${0.08+pulse*0.12})`;
        ctx.fill();
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI*2);
        ctx.fillStyle = color; ctx.fill();
      });

      // Region labels
      [
        [52, 53, "AFRIQUE",    "#F4B942"],
        [50, 22, "EUROPE",     "#7ab3f5"],
        [19, 28, "AMÉRIQUES",  "#7ab3f5"],
        [70, 22, "ASIE",       "#5a8ad4"],
      ].forEach(([px, py, lbl, color]) => {
        ctx.save();
        ctx.font = `bold ${Math.max(9, W*0.018)}px 'Exo 2', Arial`;
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.45;
        ctx.textAlign = "center";
        ctx.fillText(lbl, px*W/100, py*H/100);
        ctx.restore();
      });

      tick++;
      animId = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animId);
  }, []);

  return (
    <div style={{ position:"relative" }}>
      <canvas
        ref={canvasRef}
        width={700}
        height={400}
        style={{ width:"100%", height:"auto", borderRadius:14, display:"block", border:"1px solid rgba(39,118,234,0.2)" }}
      />
    </div>
  );
}

// ============================================================
// MAIN APP
// ============================================================
export default function MemberSync() {
  const [lang, setLang] = useState(0); // 0=FR (default), 1=EN
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const navLinks = [
    { id:"hero",         label: T.nav.home },
    { id:"features",     label: T.nav.features },
    { id:"solutions",    label: T.nav.solutions },
    { id:"pricing",      label: T.nav.pricing },
    { id:"how-it-works", label: T.nav.howItWorks },
    { id:"about",        label: T.nav.about },
    { id:"contact",      label: T.nav.contact },
  ];

  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior:"smooth" });
    setMobileOpen(false);
  };

  const PHONE   = "+237 6 58 50 48 15";
  const EMAIL   = "support@memberssync.com";
  const WA_LINK = "https://wa.me/237658504815";

  const Btn = ({ children, onClick, variant="gold", small=false }) => {
    const base = {
      fontFamily:"'Exo 2',sans-serif", fontWeight:700, cursor:"pointer",
      border:"none", borderRadius:10, display:"inline-flex",
      alignItems:"center", gap:"0.5rem", transition:"all 0.2s",
      padding: small ? "0.45rem 1.1rem" : "0.85rem 2rem",
      fontSize: small ? "0.83rem" : "0.95rem",
      textDecoration:"none",
    };
    const styles = {
      gold:    { ...base, background:"#F4B942", color:"#0D1B2A" },
      outline: { ...base, background:"transparent", color:"white", border:"2px solid rgba(255,255,255,0.45)" },
      blue:    { ...base, background:"var(--blue)", color:"white" },
    };
    return <button style={styles[variant] || styles.gold} onClick={onClick}>{children}</button>;
  };

  return (
    <div style={{ fontFamily:"'Exo 2','Segoe UI',sans-serif", overflowX:"hidden", background:"#fff" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@300;400;500;600;700;800;900&display=swap');
        *, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
        html { scroll-behavior:smooth; }
        body { overflow-x:hidden; }
        :root {
          --blue:#2776EA; --darkblue:#1e2a6e; --red:#E8192C; --gold:#F4B942;
          --dark:#0D1B2A; --light:#EEF4FF; --lighter:#F8FAFF;
          --border:rgba(39,118,234,0.13);
          --shadow:0 20px 60px rgba(39,118,234,0.15);
          --shadow-sm:0 4px 20px rgba(39,118,234,0.08);
        }
        .stag { display:inline-block; background:var(--light); color:var(--blue); font-size:0.73rem; font-weight:700; letter-spacing:2px; text-transform:uppercase; padding:0.4rem 1.2rem; border-radius:50px; border:1px solid var(--border); margin-bottom:1rem; }
        .stag-inv { display:inline-block; background:rgba(255,255,255,0.1); color:#F4B942; font-size:0.73rem; font-weight:700; letter-spacing:2px; text-transform:uppercase; padding:0.4rem 1.2rem; border-radius:50px; border:1px solid rgba(244,185,66,0.3); margin-bottom:1rem; }
        .stitle { font-family:'Exo 2',sans-serif; font-size:clamp(1.7rem,3.5vw,2.7rem); font-weight:800; color:var(--dark); line-height:1.15; letter-spacing:-0.5px; margin-bottom:1rem; }
        .stitle-inv { font-family:'Exo 2',sans-serif; font-size:clamp(1.7rem,3.5vw,2.7rem); font-weight:800; color:white; line-height:1.15; letter-spacing:-0.5px; margin-bottom:1rem; }
        .ssub { font-size:1rem; color:#5a7a9a; max-width:580px; line-height:1.8; }
        .ssub-inv { font-size:1rem; color:rgba(255,255,255,0.72); max-width:580px; line-height:1.8; }
        .card { background:white; border:1px solid var(--border); border-radius:16px; padding:2rem; transition:all 0.3s; }
        .card:hover { transform:translateY(-5px); box-shadow:var(--shadow); }
        @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-10px)} }
        @keyframes pdot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.6;transform:scale(1.3)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }

        /* ---- RESPONSIVE ---- */
        @media (max-width:900px) {
          .nav-links,.nav-actions { display:none !important; }
          .hamburger { display:flex !important; }
          .hero-grid { grid-template-columns:1fr !important; }
          .grid-2,.about-grid { grid-template-columns:1fr !important; }
          .grid-3 { grid-template-columns:1fr 1fr !important; }
          .grid-4 { grid-template-columns:1fr 1fr !important; }
          .footer-grid { grid-template-columns:1fr 1fr !important; }
          .pricing-grid { grid-template-columns:1fr !important; max-width:400px; margin-left:auto; margin-right:auto; }
          .steps-grid { grid-template-columns:1fr !important; }
          .hero-text { text-align:center !important; }
          .hero-text .ssub { margin:0 auto; }
          .hero-btns { justify-content:center !important; }
          .hero-contact { align-items:center !important; }
          .center-mob { text-align:center !important; }
          .center-mob .ssub { margin:0 auto; }
          .contact-grid { grid-template-columns:1fr !important; }
        }
        @media (max-width:540px) {
          .grid-3 { grid-template-columns:1fr !important; }
          .footer-grid { grid-template-columns:1fr !important; }
        }
      `}</style>

      {/* ===== NAVBAR ===== */}
      <nav style={{ position:"fixed", top:0, width:"100%", zIndex:1000, background:scrolled?"rgba(255,255,255,0.98)":"rgba(255,255,255,0.95)", backdropFilter:"blur(20px)", borderBottom:"1px solid var(--border)", boxShadow:scrolled?"0 2px 20px rgba(39,118,234,0.1)":"none", transition:"all 0.3s" }}>
        <div style={{ maxWidth:1400, margin:"0 auto", padding:"0 1.5rem", display:"flex", justifyContent:"space-between", alignItems:"center", height:68 }}>
          {/* Logo */}
          <div onClick={() => scrollTo("hero")} style={{ display:"flex", alignItems:"center", gap:"0.7rem", cursor:"pointer" }}>
            <NSLogo size={44} />
            <div>
              <div style={{ fontFamily:"'Exo 2',sans-serif", fontWeight:900, fontSize:"1.35rem", lineHeight:1, color:"var(--dark)" }}>
                Member<span style={{ color:"var(--blue)" }}>Sync</span>
              </div>
              <div style={{ fontSize:"0.6rem", color:"#8a9ab8", fontWeight:500, letterSpacing:"0.5px", textTransform:"uppercase" }}>by NextSolutions</div>
            </div>
          </div>

          {/* Desktop links */}
          <div className="nav-links" style={{ display:"flex", alignItems:"center", gap:"1.6rem" }}>
            {navLinks.map(l => (
              <button key={l.id} onClick={() => scrollTo(l.id)}
                onMouseEnter={e => e.currentTarget.style.color="var(--blue)"}
                onMouseLeave={e => e.currentTarget.style.color="#334"}
                style={{ background:"none", border:"none", cursor:"pointer", color:"#334", fontWeight:500, fontSize:"0.87rem", fontFamily:"'Exo 2',sans-serif", padding:"0.3rem 0", transition:"color 0.2s" }}>
                {tr(l.label, lang)}
              </button>
            ))}
          </div>

          {/* Desktop actions */}
          <div className="nav-actions" style={{ display:"flex", alignItems:"center", gap:"0.8rem" }}>
            <div style={{ display:"flex", background:"var(--lighter)", borderRadius:8, padding:2, border:"1px solid var(--border)" }}>
              {["FR","EN"].map((l,i) => (
                <button key={l} onClick={() => setLang(i)} style={{
                  background:lang===i?"var(--blue)":"none", color:lang===i?"white":"#8a9ab8",
                  border:"none", padding:"0.25rem 0.7rem", borderRadius:6,
                  fontSize:"0.76rem", fontWeight:700, cursor:"pointer",
                  fontFamily:"'Exo 2',sans-serif", transition:"all 0.2s",
                }}>{l}</button>
              ))}
            </div>
            <button style={{ background:"transparent", color:"var(--blue)", padding:"0.45rem 1.2rem", borderRadius:10, border:"2px solid var(--blue)", fontWeight:700, fontSize:"0.85rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }}
              onClick={() => window.location.href="/signup"}>{lang===0 ? "S'inscrire" : "Register"}</button>
            <button style={{ background:"#F4B942", color:"#0D1B2A", padding:"0.45rem 1.2rem", borderRadius:10, border:"none", fontWeight:700, fontSize:"0.85rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }}
              onClick={() => scrollTo("contact")}>{tr(T.nav.demo, lang)}</button>
          </div>

          {/* Hamburger */}
          <button className="hamburger" onClick={() => setMobileOpen(o => !o)}
            style={{ display:"none", background:"none", border:"none", cursor:"pointer", flexDirection:"column", gap:5, padding:4 }}>
            {[0,1,2].map(i => <span key={i} style={{ display:"block", width:24, height:2.5, background:"var(--dark)", borderRadius:2 }} />)}
          </button>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div style={{ position:"absolute", top:68, left:0, right:0, background:"white", borderBottom:"1px solid var(--border)", padding:"1rem 1.5rem 1.5rem", boxShadow:"0 8px 30px rgba(0,0,0,0.1)", zIndex:999 }}>
            {navLinks.map(l => (
              <button key={l.id} onClick={() => scrollTo(l.id)} style={{ display:"block", width:"100%", textAlign:"left", background:"none", border:"none", cursor:"pointer", color:"var(--dark)", fontWeight:500, fontSize:"1rem", padding:"0.7rem 0", borderBottom:"1px solid var(--border)", fontFamily:"'Exo 2',sans-serif" }}>
                {tr(l.label, lang)}
              </button>
            ))}
            <div style={{ display:"flex", gap:"0.5rem", marginTop:"1rem", alignItems:"center" }}>
              {["FR","EN"].map((l,i) => (
                <button key={l} onClick={() => { setLang(i); setMobileOpen(false); }} style={{ background:lang===i?"var(--blue)":"none", color:lang===i?"white":"#666", border:"1px solid var(--border)", padding:"0.3rem 0.9rem", borderRadius:6, fontSize:"0.8rem", cursor:"pointer", fontWeight:700 }}>{l}</button>
              ))}
              <button style={{ background:"transparent", color:"var(--blue)", padding:"0.45rem 1.2rem", borderRadius:10, border:"2px solid var(--blue)", fontWeight:700, fontSize:"0.85rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }}
                onClick={() => { window.location.href="/signup"; setMobileOpen(false); }}>{lang===0 ? "S'inscrire" : "Register"}</button>
              <button style={{ marginLeft:"auto", background:"#F4B942", color:"#0D1B2A", padding:"0.45rem 1.2rem", borderRadius:10, border:"none", fontWeight:700, fontSize:"0.85rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }}
                onClick={() => scrollTo("contact")}>{tr(T.nav.demo, lang)}</button>
            </div>
          </div>
        )}
      </nav>

      {/* ===== HERO ===== */}
      <section id="hero" style={{ minHeight:"100vh", paddingTop:68, background:"linear-gradient(135deg,#060d1e 0%,#0e1f52 45%,#1a3a8c 75%,#2776EA 100%)", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, backgroundImage:"radial-gradient(rgba(255,255,255,0.035) 1px, transparent 1px)", backgroundSize:"28px 28px", pointerEvents:"none" }} />

        <div style={{ maxWidth:1400, margin:"0 auto", padding:"2.5rem 1.5rem", position:"relative", zIndex:1 }}>
          {/* Badge */}
          <div style={{ textAlign:"center", marginBottom:"2rem" }}>
            <span style={{ display:"inline-flex", alignItems:"center", gap:"0.5rem", background:"rgba(244,185,66,0.12)", border:"1px solid rgba(244,185,66,0.3)", padding:"0.35rem 1.2rem", borderRadius:50, fontSize:"0.77rem", color:"#F4B942", fontWeight:600, letterSpacing:1, textTransform:"uppercase" }}>
              <span style={{ width:6, height:6, background:"#F4B942", borderRadius:"50%", animation:"pdot 2s infinite" }} />
              {tr(T.hero.badge, lang)}
            </span>
          </div>

          <div className="hero-grid" style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"3rem", alignItems:"center" }}>
            {/* Text */}
            <div className="hero-text">
              <h1 style={{ fontFamily:"'Exo 2',sans-serif", fontWeight:900, color:"white", fontSize:"clamp(2.3rem,5vw,3.7rem)", lineHeight:1.1, letterSpacing:-1, marginBottom:"1.5rem" }}>
                {tr(T.hero.title1,lang)}<br/>
                <span style={{ color:"#F4B942" }}>{tr(T.hero.title2,lang)}</span><br/>
                {tr(T.hero.title3,lang)}
              </h1>
              <p className="ssub-inv" style={{ maxWidth:500, marginBottom:"2.5rem" }}>{tr(T.hero.sub,lang)}</p>
              <div className="hero-btns" style={{ display:"flex", gap:"1rem", flexWrap:"wrap", marginBottom:"2rem" }}>
                <button style={{ background:"#F4B942", color:"#0D1B2A", padding:"0.85rem 2rem", borderRadius:10, border:"none", fontWeight:700, fontSize:"0.95rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }} onClick={() => scrollTo("contact")}>{tr(T.hero.cta1,lang)} →</button>
                <button style={{ background:"transparent", color:"white", padding:"0.85rem 2rem", borderRadius:10, border:"2px solid rgba(255,255,255,0.4)", fontWeight:600, fontSize:"0.95rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }} onClick={() => scrollTo("pricing")}>{tr(T.hero.cta2,lang)}</button>
              </div>
              <div className="hero-contact" style={{ display:"flex", flexDirection:"column", gap:"0.45rem" }}>
                <a href={WA_LINK} style={{ color:"rgba(255,255,255,0.7)", textDecoration:"none", fontSize:"0.88rem", display:"flex", alignItems:"center", gap:"0.5rem" }}>💬 WhatsApp : {PHONE}</a>
                <a href={`mailto:${EMAIL}`} style={{ color:"rgba(255,255,255,0.7)", textDecoration:"none", fontSize:"0.88rem", display:"flex", alignItems:"center", gap:"0.5rem" }}>✉️ {EMAIL}</a>
              </div>
            </div>

            {/* Map */}
            <div style={{ animation:"float 8s ease-in-out infinite" }}>
              <WorldMap />
              <p style={{ textAlign:"center", color:"rgba(255,255,255,0.4)", fontSize:"0.73rem", marginTop:"0.7rem" }}>
                {lang===0 ? "🌍 Afrique · Europe · Amériques — MemberSync partout" : "🌍 Africa · Europe · Americas — MemberSync everywhere"}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== STATS ===== */}
      <div style={{ background:"var(--darkblue)", padding:"2.5rem 1.5rem" }}>
        <div className="grid-4" style={{ maxWidth:1200, margin:"0 auto", display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:"1.5rem", textAlign:"center" }}>
          {[["50+",T.stats.s1],["5 000+",T.stats.s2],["10+",T.stats.s3],["98%",T.stats.s4]].map(([n,l],i) => (
            <div key={i}>
              <div style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"2.2rem", fontWeight:900, color:"#F4B942" }}>{n}</div>
              <div style={{ fontSize:"0.84rem", color:"rgba(255,255,255,0.65)", marginTop:"0.25rem" }}>{tr(l,lang)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ===== PROBLEM / SOLUTION ===== */}
      <section style={{ padding:"6rem 1.5rem", background:"var(--lighter)" }}>
        <div style={{ maxWidth:1300, margin:"0 auto" }}>
          <div className="center-mob" style={{ textAlign:"center", marginBottom:"3rem" }}>
            <div className="stag">{tr(T.problem.tag,lang)}</div>
            <h2 className="stitle">{tr(T.problem.title,lang)}</h2>
          </div>
          <div className="grid-2" style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"2.5rem", alignItems:"center" }}>
            <div style={{ display:"flex", flexDirection:"column", gap:"1rem" }}>
              {[[T.problem.p1t,T.problem.p1d,"😟"],[T.problem.p2t,T.problem.p2d,"📋"],[T.problem.p3t,T.problem.p3d,"📉"]].map(([tt,dd,ic],i) => (
                <div key={i} className="card" style={{ display:"flex", gap:"1rem", alignItems:"flex-start" }}>
                  <span style={{ fontSize:"1.4rem", flexShrink:0 }}>{ic}</span>
                  <div>
                    <strong style={{ color:"var(--dark)", fontSize:"0.93rem", display:"block", marginBottom:"0.2rem" }}>{tr(tt,lang)}</strong>
                    <span style={{ color:"#5a7a9a", fontSize:"0.84rem" }}>{tr(dd,lang)}</span>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ background:"linear-gradient(135deg,#1a3a7c,#2776EA)", borderRadius:20, padding:"2.5rem", color:"white" }}>
              <h3 style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"1.7rem", fontWeight:800, marginBottom:"1rem" }}>{tr(T.problem.solTitle,lang)}</h3>
              <p style={{ color:"rgba(255,255,255,0.8)", lineHeight:1.8, marginBottom:"1.5rem" }}>{tr(T.problem.solDesc,lang)}</p>
              {[T.problem.check1,T.problem.check2,T.problem.check3,T.problem.check4].map((c,i) => (
                <div key={i} style={{ display:"flex", alignItems:"center", gap:"0.8rem", marginBottom:"0.7rem" }}>
                  <span style={{ width:22, height:22, background:"#F4B942", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"0.7rem", fontWeight:700, color:"#0D1B2A", flexShrink:0 }}>✓</span>
                  <span style={{ fontSize:"0.9rem", color:"rgba(255,255,255,0.9)" }}>{tr(c,lang)}</span>
                </div>
              ))}
              <button style={{ marginTop:"1.5rem", background:"#F4B942", color:"#0D1B2A", padding:"0.85rem 2rem", borderRadius:10, border:"none", fontWeight:700, fontSize:"0.95rem", fontFamily:"'Exo 2',sans-serif", cursor:"pointer" }} onClick={() => scrollTo("contact")}>{tr(T.hero.cta1,lang)} →</button>
            </div>
          </div>
        </div>
      </section>

      {/* ===== FEATURES ===== */}
      <section id="features" style={{ padding:"6rem 1.5rem" }}>
        <div style={{ maxWidth:1300, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:"3rem" }}>
            <div className="stag">{tr(T.features.tag,lang)}</div>
            <h2 className="stitle">{tr(T.features.title,lang)}</h2>
            <p className="ssub" style={{ margin:"0 auto" }}>{tr(T.features.sub,lang)}</p>
          </div>
          <div className="grid-3" style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:"1.5rem" }}>
            {T.features.f.map((f,i) => (
              <div key={i} className="card" style={{ position:"relative", overflow:"hidden" }}>
                <div style={{ position:"absolute", top:0, left:0, right:0, height:3, background:"linear-gradient(90deg,var(--blue),var(--darkblue))" }} />
                <div style={{ fontSize:"2rem", marginBottom:"1rem" }}>{f.icon}</div>
                <h3 style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"1rem", fontWeight:700, color:"var(--dark)", marginBottom:"0.6rem" }}>{tr(f.t,lang)}</h3>
                <p style={{ fontSize:"0.86rem", color:"#5a7a9a", lineHeight:1.7 }}>{tr(f.d,lang)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== HOW IT WORKS ===== */}
      <section id="how-it-works" style={{ padding:"6rem 1.5rem", background:"linear-gradient(135deg,#060d1e,#1a3a7c)" }}>
        <div style={{ maxWidth:1100, margin:"0 auto", textAlign:"center" }}>
          <div className="stag-inv">{tr(T.howItWorks.tag,lang)}</div>
          <h2 className="stitle-inv" style={{ margin:"0 auto 3rem" }}>{tr(T.howItWorks.title,lang)}</h2>
          <div className="steps-grid" style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:"2rem" }}>
            {T.howItWorks.steps.map((s,i) => (
              <div key={i} style={{ background:"rgba(255,255,255,0.06)", border:"1px solid rgba(255,255,255,0.12)", borderRadius:18, padding:"2.5rem 2rem" }}>
                <div style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"3rem", fontWeight:900, color:"rgba(244,185,66,0.2)", lineHeight:1, marginBottom:"0.5rem" }}>{s.n}</div>
                <h3 style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"1.05rem", fontWeight:700, color:"white", marginBottom:"0.8rem" }}>{tr(s.t,lang)}</h3>
                <p style={{ fontSize:"0.86rem", color:"rgba(255,255,255,0.68)", lineHeight:1.7 }}>{tr(s.d,lang)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== SOLUTIONS ===== */}
      <section id="solutions" style={{ padding:"6rem 1.5rem", background:"var(--lighter)" }}>
        <div style={{ maxWidth:1300, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:"3rem" }}>
            <div className="stag">{tr(T.solutions.tag,lang)}</div>
            <h2 className="stitle">{tr(T.solutions.title,lang)}</h2>
            <p className="ssub" style={{ margin:"0 auto" }}>{tr(T.solutions.sub,lang)}</p>
          </div>
          <div className="grid-3" style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:"1.5rem" }}>
            {T.solutions.sectors.map((s,i) => (
              <div key={i} className="card" style={{ textAlign:"center" }}>
                <div style={{ fontSize:"2.4rem", marginBottom:"1rem" }}>{s.icon}</div>
                <h3 style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"1rem", fontWeight:700, color:"var(--dark)", marginBottom:"0.6rem" }}>{tr(s.t,lang)}</h3>
                <p style={{ fontSize:"0.84rem", color:"#5a7a9a", lineHeight:1.6 }}>{tr(s.d,lang)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== PRICING ===== */}
      <section id="pricing" style={{ padding:"6rem 1.5rem" }}>
        <div style={{ maxWidth:1100, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:"3rem" }}>
            <div className="stag">{tr(T.pricing.tag,lang)}</div>
            <h2 className="stitle">{tr(T.pricing.title,lang)}</h2>
            <p className="ssub" style={{ margin:"0 auto" }}>{tr(T.pricing.sub,lang)}</p>
          </div>
          <div className="pricing-grid" style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:"1.5rem", alignItems:"start" }}>
            {T.pricing.plans.map((plan,i) => (
              <div key={i} style={{ background:"white", border:plan.popular?"2px solid var(--blue)":"1px solid var(--border)", borderRadius:20, overflow:"hidden", transform:plan.popular?"scale(1.03)":"scale(1)", boxShadow:plan.popular?"0 0 0 4px rgba(39,118,234,0.07)":"none" }}>
                {plan.popular && <div style={{ background:"var(--blue)", color:"white", textAlign:"center", padding:"0.45rem", fontSize:"0.72rem", fontWeight:700, letterSpacing:1, textTransform:"uppercase" }}>⭐ {tr(["Le plus populaire","Most popular"],lang)}</div>}
                <div style={{ padding:"2rem", textAlign:"center", borderBottom:"1px solid var(--border)" }}>
                  <div style={{ fontSize:"2rem", marginBottom:"0.8rem" }}>{plan.icon}</div>
                  <div style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"1.2rem", fontWeight:800, color:"var(--dark)", marginBottom:"0.4rem" }}>{tr(plan.name,lang)}</div>
                  <div style={{ fontSize:"0.82rem", color:"#5a7a9a", marginBottom:"1.2rem" }}>{tr(plan.desc,lang)}</div>
                  <div style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"1.5rem", fontWeight:800, color:"var(--blue)" }}>{tr(plan.price,lang)}</div>
                  <div style={{ fontSize:"0.77rem", color:"#7a9ab8", marginTop:"0.3rem" }}>{tr(["Devis personnalisé","Custom quote"],lang)}</div>
                </div>
                <div style={{ padding:"1.5rem 2rem 2rem" }}>
                  <div style={{ display:"flex", flexDirection:"column", gap:"0.65rem", marginBottom:"1.5rem" }}>
                    {plan.features.map((f,j) => (
                      <div key={j} style={{ display:"flex", alignItems:"flex-start", gap:"0.65rem", fontSize:"0.86rem", color:"#334" }}>
                        <span style={{ color:"var(--blue)", fontWeight:700, flexShrink:0 }}>✓</span>{tr(f,lang)}
                      </div>
                    ))}
                  </div>
                  <button onClick={() => scrollTo("contact")} style={{ display:"block", width:"100%", padding:"0.85rem", borderRadius:10, fontWeight:700, fontSize:"0.93rem", cursor:"pointer", fontFamily:"'Exo 2',sans-serif", background:plan.ctaStyle==="accent"?"var(--blue)":plan.ctaStyle==="gold"?"#F4B942":"transparent", color:plan.ctaStyle==="accent"?"white":plan.ctaStyle==="gold"?"#0D1B2A":"var(--blue)", border:plan.ctaStyle==="outline"?"2px solid var(--blue)":"none", transition:"all 0.2s" }}>{tr(plan.cta,lang)}</button>
                </div>
              </div>
            ))}
          </div>
          <p style={{ textAlign:"center", color:"#5a7a9a", fontSize:"0.85rem", marginTop:"2rem" }}>ℹ️ {tr(T.pricing.note,lang)}</p>
        </div>
      </section>

      {/* ===== TESTIMONIALS ===== */}
      <section style={{ padding:"6rem 1.5rem", background:"linear-gradient(135deg,var(--lighter),#e4edff)" }}>
        <div style={{ maxWidth:1300, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:"3rem" }}>
            <div className="stag">{tr(T.testimonials.tag,lang)}</div>
            <h2 className="stitle">{tr(T.testimonials.title,lang)}</h2>
          </div>
          <div className="grid-2" style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:"1.5rem" }}>
            {T.testimonials.reviews.map((r,i) => (
              <div key={i} className="card">
                <div style={{ display:"flex", gap:"1rem", alignItems:"flex-start", marginBottom:"1rem" }}>
                  <div style={{ width:50, height:50, background:"var(--light)", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"1.4rem", flexShrink:0 }}>{r.avatar}</div>
                  <div>
                    <div style={{ fontWeight:700, color:"var(--dark)", fontSize:"0.93rem" }}>{r.name}</div>
                    <div style={{ fontSize:"0.77rem", color:"#5a7a9a" }}>{tr(r.role,lang)}</div>
                    <div style={{ color:"#F4B942", fontSize:"0.83rem", marginTop:"0.2rem" }}>★★★★★</div>
                  </div>
                </div>
                <p style={{ fontSize:"0.89rem", color:"#445", lineHeight:1.7, fontStyle:"italic" }}>"{tr(r.text,lang)}"</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== ABOUT ===== */}
      <section id="about" style={{ padding:"6rem 1.5rem" }}>
        <div style={{ maxWidth:1200, margin:"0 auto" }}>
          <div className="about-grid" style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"4rem", alignItems:"center" }}>
            <div>
              <div className="stag">{tr(T.about.tag,lang)}</div>
              <h2 className="stitle">{tr(T.about.title,lang)}</h2>
              <p style={{ color:"#5a7a9a", lineHeight:1.8, marginBottom:"1.5rem" }}>{tr(T.about.desc,lang)}</p>
              <div style={{ background:"var(--light)", borderRadius:14, padding:"1.4rem 1.6rem", borderLeft:"4px solid var(--blue)", marginBottom:"1rem" }}>
                <strong style={{ color:"var(--blue)", fontSize:"0.75rem", fontWeight:700, letterSpacing:1, textTransform:"uppercase" }}>🎯 Mission</strong>
                <p style={{ color:"var(--dark)", fontSize:"0.87rem", lineHeight:1.7, marginTop:"0.4rem" }}>{tr(T.about.mission,lang)}</p>
              </div>
              <div style={{ background:"var(--light)", borderRadius:14, padding:"1.4rem 1.6rem", borderLeft:"4px solid #F4B942" }}>
                <strong style={{ color:"#b8830a", fontSize:"0.75rem", fontWeight:700, letterSpacing:1, textTransform:"uppercase" }}>🔭 Vision</strong>
                <p style={{ color:"var(--dark)", fontSize:"0.87rem", lineHeight:1.7, marginTop:"0.4rem" }}>{tr(T.about.vision,lang)}</p>
              </div>
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:"1.5rem" }}>
              {/* Real photo from Don William Barbershop */}
              <div style={{ borderRadius:16, overflow:"hidden", border:"1px solid var(--border)", boxShadow:"var(--shadow-sm)" }}>
                <img
                  src="/a1.jpeg"
                  alt="Don William Barbershop — MemberSync en action"
                  style={{ width:"100%", height:210, objectFit:"cover", display:"block" }}
                  onError={e => { e.currentTarget.style.display="none"; e.currentTarget.nextSibling.style.display="flex"; }}
                />
                <div style={{ display:"none", width:"100%", height:210, background:"var(--light)", alignItems:"center", justifyContent:"center", fontSize:"4rem" }}>✂️</div>
                <div style={{ padding:"0.9rem 1.2rem", background:"white" }}>
                  <div style={{ fontSize:"0.81rem", color:"#5a7a9a" }}>📍 {lang===0 ? "Don William Barbershop — Salon partenaire MemberSync, Yaoundé" : "Don William Barbershop — MemberSync Partner Salon, Yaoundé"}</div>
                </div>
              </div>

              {/* NS brand card */}
              <div style={{ background:"linear-gradient(135deg,#0a1228,#1e2a6e,#2776EA)", borderRadius:16, padding:"2rem", textAlign:"center", color:"white" }}>
                <div style={{ display:"flex", justifyContent:"center", marginBottom:"1rem" }}>
                  <NSLogo size={56} />
                </div>
                <div style={{ fontFamily:"'Exo 2',sans-serif", fontWeight:900, fontSize:"1.25rem" }}>NEXT SOLUTIONS</div>
                <div style={{ color:"rgba(255,255,255,0.6)", fontSize:"0.8rem", marginTop:"0.4rem", fontStyle:"italic" }}>Innovation deserves performance</div>
                <div style={{ display:"flex", justifyContent:"center", gap:"1rem", marginTop:"1.2rem" }}>
                  {[{href:"https://www.facebook.com/share/1AefsKtL7p/",icon:"f"},{href:"https://www.linkedin.com/company/nexts-solutions/",icon:"in"},{href:"https://youtube.com/@membersync",icon:"▶"}].map((s,i) => (
                    <a key={i} href={s.href} target="_blank" rel="noopener" style={{ width:34, height:34, border:"1px solid rgba(255,255,255,0.25)", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", color:"rgba(255,255,255,0.7)", textDecoration:"none", fontWeight:900, fontSize:"0.75rem" }}>{s.icon}</a>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== CONTACT ===== */}
      <section id="contact" style={{ padding:"6rem 1.5rem", background:"linear-gradient(135deg,#060d1e,#1a3a7c)" }}>
        <div style={{ maxWidth:900, margin:"0 auto", textAlign:"center" }}>
          <div className="stag-inv">{tr(T.contact.tag,lang)}</div>
          <h2 className="stitle-inv">{tr(T.contact.title,lang)}</h2>
          <p className="ssub-inv" style={{ margin:"0 auto 3rem" }}>{tr(T.contact.sub,lang)}</p>
          <div className="contact-grid" style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:"1rem", marginBottom:"2.5rem" }}>
            <a href={WA_LINK} target="_blank" rel="noopener" style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:"0.6rem", background:"#25D366", color:"white", padding:"1.5rem", borderRadius:14, textDecoration:"none", fontWeight:600, fontSize:"0.87rem" }}>
              <span style={{ fontSize:"1.8rem" }}>💬</span>
              {tr(T.contact.wa,lang)}<br/><span style={{ fontSize:"0.8rem", opacity:0.9 }}>{PHONE}</span>
            </a>
            <a href={`mailto:${EMAIL}`} style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:"0.6rem", background:"rgba(255,255,255,0.08)", border:"1px solid rgba(255,255,255,0.18)", color:"white", padding:"1.5rem", borderRadius:14, textDecoration:"none", fontWeight:600, fontSize:"0.87rem" }}>
              <span style={{ fontSize:"1.8rem" }}>✉️</span>
              {tr(T.contact.email,lang)}<br/><span style={{ fontSize:"0.8rem", opacity:0.8 }}>{EMAIL}</span>
            </a>
            <a href="/login" style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:"0.6rem", background:"#F4B942", color:"#0D1B2A", padding:"1.5rem", borderRadius:14, textDecoration:"none", fontWeight:700, fontSize:"0.87rem" }}>
              <span style={{ fontSize:"1.8rem" }}>🚀</span>
              {tr(T.contact.demo,lang)}<br/><span style={{ fontSize:"0.8rem", opacity:0.8 }}>Se connecter</span>
            </a>
          </div>
          <div style={{ display:"flex", justifyContent:"center", gap:"1rem", flexWrap:"wrap" }}>
            {[{href:"https://www.facebook.com/share/1AefsKtL7p/",label:"Facebook",icon:"f"},{href:"https://www.linkedin.com/company/nexts-solutions/",label:"LinkedIn",icon:"in"},{href:"https://youtube.com/@membersync?si=39mXeHsjiiHTcSDm",label:"YouTube",icon:"▶"}].map((s,i) => (
              <a key={i} href={s.href} target="_blank" rel="noopener"
                onMouseEnter={e => e.currentTarget.style.background="rgba(255,255,255,0.16)"}
                onMouseLeave={e => e.currentTarget.style.background="rgba(255,255,255,0.08)"}
                style={{ display:"inline-flex", alignItems:"center", gap:"0.5rem", background:"rgba(255,255,255,0.08)", border:"1px solid rgba(255,255,255,0.18)", color:"white", padding:"0.55rem 1.2rem", borderRadius:30, textDecoration:"none", fontWeight:600, fontSize:"0.84rem", transition:"background 0.2s" }}>
                <span style={{ fontWeight:900 }}>{s.icon}</span> {s.label}
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer style={{ background:"var(--dark)", color:"rgba(255,255,255,0.6)", padding:"4rem 1.5rem 2rem" }}>
        <div style={{ maxWidth:1300, margin:"0 auto" }}>
          <div className="footer-grid" style={{ display:"grid", gridTemplateColumns:"2fr 1fr 1fr 1fr", gap:"2.5rem", marginBottom:"3rem" }}>
            <div>
              <div style={{ display:"flex", alignItems:"center", gap:"0.7rem", marginBottom:"1rem" }}>
                <NSLogo size={40} />
                <div style={{ fontFamily:"'Exo 2',sans-serif", fontWeight:900, fontSize:"1.25rem", color:"white" }}>Member<span style={{ color:"var(--blue)" }}>Sync</span></div>
              </div>
              <p style={{ fontSize:"0.84rem", lineHeight:1.8, maxWidth:240, color:"rgba(255,255,255,0.5)" }}>{tr(T.footer.desc,lang)}</p>
              <div style={{ marginTop:"1rem", display:"flex", flexDirection:"column", gap:"0.4rem" }}>
                <a href={WA_LINK} style={{ color:"rgba(255,255,255,0.5)", textDecoration:"none", fontSize:"0.82rem" }}>💬 {PHONE}</a>
                <a href={`mailto:${EMAIL}`} style={{ color:"rgba(255,255,255,0.5)", textDecoration:"none", fontSize:"0.82rem" }}>✉️ {EMAIL}</a>
                <a href="https://memberssync.com" style={{ color:"rgba(255,255,255,0.5)", textDecoration:"none", fontSize:"0.82rem" }}>🌐 memberssync.com</a>
              </div>
            </div>
            {[
              { title:T.footer.product, links:[[tr(T.nav.features,lang),"features"],[tr(T.nav.solutions,lang),"solutions"],[tr(T.nav.pricing,lang),"pricing"],[tr(T.nav.howItWorks,lang),"how-it-works"]] },
              { title:T.footer.company, links:[[tr(T.nav.about,lang),"about"],[tr(T.nav.contact,lang),"contact"]] },
              { title:T.footer.support, links:[["WhatsApp","contact"],["Email","contact"],["memberssync.com","contact"]] },
            ].map((col,i) => (
              <div key={i}>
                <h4 style={{ fontFamily:"'Exo 2',sans-serif", fontSize:"0.88rem", fontWeight:700, color:"white", marginBottom:"1rem" }}>{tr(col.title,lang)}</h4>
                <ul style={{ listStyle:"none", display:"flex", flexDirection:"column", gap:"0.6rem" }}>
                  {col.links.map(([label,id],j) => (
                    <li key={j}><button onClick={() => scrollTo(id)}
                      onMouseEnter={e => e.currentTarget.style.color="white"}
                      onMouseLeave={e => e.currentTarget.style.color="rgba(255,255,255,0.5)"}
                      style={{ background:"none", border:"none", cursor:"pointer", color:"rgba(255,255,255,0.5)", textDecoration:"none", fontSize:"0.83rem", transition:"color 0.2s", fontFamily:"'Exo 2',sans-serif" }}>{label}</button></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div style={{ borderTop:"1px solid rgba(255,255,255,0.08)", paddingTop:"2rem", display:"flex", justifyContent:"space-between", alignItems:"center", flexWrap:"wrap", gap:"1rem" }}>
            <p style={{ fontSize:"0.79rem" }}>© {new Date().getFullYear()} MemberSync. {tr(T.footer.rights,lang)}</p>
            <div style={{ display:"flex", gap:"0.8rem" }}>
              {[{href:"https://www.facebook.com/share/1AefsKtL7p/",icon:"f"},{href:"https://www.linkedin.com/company/nexts-solutions/",icon:"in"},{href:"https://youtube.com/@membersync",icon:"▶"}].map((s,i) => (
                <a key={i} href={s.href} target="_blank" rel="noopener" style={{ width:30, height:30, border:"1px solid rgba(255,255,255,0.18)", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", color:"rgba(255,255,255,0.55)", textDecoration:"none", fontSize:"0.73rem", fontWeight:900 }}>{s.icon}</a>
              ))}
            </div>
            <p style={{ fontSize:"0.79rem", color:"rgba(255,255,255,0.35)" }}>{tr(T.footer.powered,lang)} <strong style={{ color:"rgba(255,255,255,0.65)" }}>NextSolutions</strong></p>
          </div>
        </div>
      </footer>

      {/* ===== WhatsApp Float ===== */}
      <a href={WA_LINK} target="_blank" rel="noopener" style={{ position:"fixed", bottom:"1.5rem", right:"1.5rem", zIndex:9999, width:58, height:58, background:"#25D366", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", boxShadow:"0 6px 20px rgba(37,211,102,0.45)", textDecoration:"none", fontSize:"1.7rem", animation:"pdot 3s ease-in-out infinite" }}>💬</a>
    </div>
  );
}

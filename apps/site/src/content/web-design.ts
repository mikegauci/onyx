export const webDesignPath = "/services/web-design-development";

export const webDesignPhone = {
  display: "+356 9925 6511",
  international: "+35699256511",
} as const;

export const webDesignPackages = [
  {
    name: "Bronze",
    price: "€300",
    type: "Small business website",
    description: "Launch or refresh your business website with a choice of ready-made layouts.",
    features: [
      "Up to five mobile-friendly pages",
      "Light editing of your supplied text and photos",
      "Basic SEO setup",
      "Enquiry form and click-to-WhatsApp",
      "One round of revisions",
    ],
  },
  {
    name: "Silver",
    price: "€750",
    type: "Business website",
    description:
      "A new site or redesign with more room for your services and more design flexibility.",
    features: [
      "Up to 10 mobile-friendly pages",
      "Flexible layouts tailored to your business",
      "Copywriting from your brief",
      "On-page SEO and an enquiry form",
    ],
  },
  {
    name: "Gold",
    price: "€1,500",
    type: "Shop, bookings or listings",
    description: "A site where customers can shop, book or browse what you have available.",
    features: [
      "One shop, booking or listings setup",
      "One standard integration",
      "Catalogue scope agreed in your quote",
    ],
  },
  {
    name: "Onyx",
    price: "€3,500",
    type: "Custom web application",
    description: "A web app, client portal or marketplace designed around the way you work.",
    features: [
      "Custom interface and development",
      "Accounts and workflows scoped to your brief",
      "Integrations scoped in your quote",
    ],
  },
] as const;

export type WebDesignPackageName = (typeof webDesignPackages)[number]["name"];

type WebDesignProject = {
  name: string;
  website: string;
  type: string;
  packageName: WebDesignPackageName;
  screenshot: { src: string; height: number; alt: string };
  technologies: readonly string[];
  description: string;
};

export const webDesignProjects = [
  {
    name: "Pantrila",
    packageName: "Onyx",
    website: "https://pantrila.com/",
    type: "AI web app",
    screenshot: {
      src: "/portfolio/pantrila.webp",
      height: 800,
      alt: "Pantrila homepage introducing the cooking assistant alongside a preview of the app.",
    },
    technologies: ["Next.js", "TypeScript", "Tailwind CSS", "FastAPI", "LangGraph", "Supabase"],
    description:
      "A cooking app that suggests meals from what you have, saves recipes from links or photos, and turns a weekly meal plan into a shopping list.",
  },
  {
    name: "QTM Detailing",
    packageName: "Gold",
    website: "https://www.qtmdetailing.mt/",
    type: "Service website",
    screenshot: {
      src: "/portfolio/qtm-detailing.webp",
      height: 800,
      alt: "QTM Detailing homepage with a dark car photograph and a prominent quote button.",
    },
    technologies: ["Next.js", "TypeScript", "Tailwind CSS", "Motion", "Supabase"],
    description:
      "A website for a Maltese car detailing studio with before-and-after photography, clear service packages and a route to request a quote.",
  },
  {
    name: "MaltaGuns",
    packageName: "Onyx",
    website: "https://www.maltaguns.com/",
    type: "Community platform",
    screenshot: {
      src: "/portfolio/maltaguns-homepage.webp",
      height: 761,
      alt: "MaltaGuns homepage with navigation, a headline and a photograph of Malta’s harbour.",
    },
    technologies: ["Next.js", "TypeScript", "Tailwind CSS", "Supabase", "Tiptap"],
    description:
      "A custom community platform for Malta with member accounts, event pages, a directory and an editorial section for guides and news.",
  },
  {
    name: "Rotta",
    packageName: "Gold",
    website: "https://rotta.mt/",
    type: "Automotive community platform",
    screenshot: {
      src: "/portfolio/rotta.webp",
      height: 800,
      alt: "Rotta homepage with a yellow sports car and a headline about Malta’s automotive community.",
    },
    technologies: ["Next.js", "TypeScript", "Tailwind CSS", "Supabase", "Vercel"],
    description:
      "A hub for Malta’s automotive community, with a searchable business directory, videos, events and a shop.",
  },
  {
    name: "Malta Detailing Academy",
    packageName: "Gold",
    website: "https://mda.mt/",
    type: "Training website",
    screenshot: {
      src: "/portfolio/mda.webp",
      height: 800,
      alt: "Malta Detailing Academy homepage showing hands-on training and a link to view courses.",
    },
    technologies: ["Next.js", "TypeScript", "Tailwind CSS", "Supabase", "Vercel"],
    description:
      "A course website with a custom CMS for Malta Detailing Academy’s hands-on vehicle detailing training.",
  },
  {
    name: "Jam Weddings",
    packageName: "Bronze",
    website: "https://jam.mt/",
    type: "Creative portfolio",
    screenshot: {
      src: "/portfolio/jam.webp",
      height: 800,
      alt: "Jam Weddings homepage showing a frame from the studio’s wedding film.",
    },
    technologies: ["Astro", "TypeScript", "Vercel", "Vimeo", "Mailjet"],
    description:
      "A portfolio website for a Maltese wedding photography and cinematography team, with films, photography, service packages and an enquiry form.",
  },
  {
    name: "Thrust Studio",
    packageName: "Bronze",
    website: "https://www.thruststudio.co/",
    type: "Creative portfolio",
    screenshot: {
      src: "/portfolio/thrust-studio.webp",
      height: 800,
      alt: "Thrust Studio homepage with a colourful frame from the studio’s video showreel.",
    },
    technologies: ["Astro", "TypeScript", "Vercel", "Vimeo"],
    description:
      "A video-led portfolio for a Maltese creative studio, with a responsive showreel and selected projects across videography, photography and design.",
  },
  {
    name: "Beachaven",
    packageName: "Silver",
    website: "https://www.beachavencomplex.com/",
    type: "Hospitality website",
    screenshot: {
      src: "/portfolio/beachaven.webp",
      height: 800,
      alt: "Beachaven homepage with its welcome headline over a scene from a boat in Xemxija Bay.",
    },
    technologies: ["Next.js", "React", "TypeScript", "CSS"],
    description:
      "A coastal redesign that brings Beachaven’s lido, restaurant, club and events together, with a clear route to reservation enquiries.",
  },
  {
    name: "Motor Element",
    packageName: "Gold",
    website: "https://www.motorelement.com/",
    type: "E-commerce storefront",
    screenshot: {
      src: "/portfolio/motor-element-shopify.webp",
      height: 800,
      alt: "Motor Element’s Shopify homepage showcasing custom car apparel.",
    },
    technologies: ["Shopify"],
    description:
      "A Shopify storefront showcasing custom car T-shirts, hoodies, wall art and other merchandise for automotive enthusiasts.",
  },
] as const satisfies readonly WebDesignProject[];

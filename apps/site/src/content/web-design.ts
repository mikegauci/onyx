export const webDesignPath = "/services/web-design-development";

export const webDesignPhone = {
  display: "+356 9925 6511",
  international: "+35699256511",
} as const;

export const webDesignPackages = [
  {
    name: "Bronze",
    price: "€300",
    type: "One-page website",
    description: "A focused page that explains what you do and makes it easy to get in touch.",
    features: [
      "One mobile-friendly page",
      "Light editing of supplied copy",
      "Basic SEO and an enquiry form",
    ],
  },
  {
    name: "Silver",
    price: "€750",
    type: "Business website",
    description: "A new site or a redesign with room to explain your services in detail.",
    features: [
      "Up to five pages",
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

export const webDesignProjects = [
  {
    name: "Pantrila",
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
    type: "Community platform",
    screenshot: {
      src: "/portfolio/maltaguns.webp",
      height: 761,
      alt: "MaltaGuns homepage with navigation, a headline and a photograph of Malta’s harbour.",
    },
    technologies: ["Next.js", "TypeScript", "Tailwind CSS", "Supabase", "Tiptap"],
    description:
      "A custom community platform for Malta with member accounts, event pages, a directory and an editorial section for guides and news.",
  },
] as const;

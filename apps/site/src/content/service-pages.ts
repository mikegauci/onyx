import type { ServiceSlug } from "./service-links";

type Offering = {
  id: string;
  title: string;
  description: string;
  points: readonly string[];
};

type ServicePage = {
  title: string;
  headline: readonly [string, string];
  introduction: string;
  description: string;
  offerings: readonly Offering[];
  faq: readonly { question: string; answer: string }[];
  enquiry: string;
};

export const servicePages = {
  "app-development": {
    title: "App development in Malta",
    headline: ["Apps that fit", "how people work."],
    introduction:
      "We design and build iOS and Android apps, web apps and portals for businesses in Malta and Gozo. Tell us what people need to do, and we’ll help you choose the right way to build it.",
    description:
      "Onyx Studio builds iOS and Android apps, web applications and client portals for Malta and Gozo. See the Pantrila project and request a quote.",
    offerings: [
      {
        id: "mobile-apps",
        title: "iOS and Android apps",
        description: "Give customers or staff an app they can return to on their phones.",
        points: [
          "Interface design and development",
          "Accounts, bookings and notifications",
          "App store submission support",
        ],
      },
      {
        id: "web-apps",
        title: "Web apps",
        description:
          "Build a tool people can use in the browser, on the devices they already have.",
        points: [
          "Dashboards and operational tools",
          "Workflows and connected data",
          "Responsive layouts for phone and desktop",
        ],
      },
      {
        id: "portals",
        title: "Client and staff portals",
        description: "Give people a place to see information, share documents or get work done.",
        points: [
          "Access for customers and teams",
          "Document and status updates",
          "Custom CRM features within your build",
        ],
      },
    ],
    faq: [
      {
        question: "Should I start with a mobile app or a web app?",
        answer:
          "A web app works well when people need a link they can open immediately. A mobile app makes sense for frequent use, push notifications or phone-specific features. We can help you decide during scoping.",
      },
      {
        question: "Can an app connect to tools we already use?",
        answer:
          "Yes. We can scope connections to existing tools such as your website, booking system or payment provider as part of the build.",
      },
      {
        question: "What do you need to quote for an app?",
        answer:
          "Tell us who will use it, the main jobs they need to complete, and which systems it needs to connect to. A rough list or a few sketches are enough to start.",
      },
    ],
    enquiry: "Tell us who the app is for, what they need to do and where you want it to run.",
  },
  "branding-graphic-design": {
    title: "Branding and graphic design in Malta",
    headline: ["Make your business", "recognisable."],
    introduction:
      "From your first logo to the graphics people see online and in print, we design a visual identity you can use consistently across your business.",
    description:
      "Brand identity, logo design, social graphics and print design from Onyx Studio in Malta. See work from QTM Detailing, MaltaGuns and Pantrila.",
    offerings: [
      {
        id: "brand-identity",
        title: "Brand identity and logos",
        description:
          "A visual identity that reflects what you do and gives you a clear set of choices to work with.",
        points: [
          "Logo and mark design",
          "Colour and typography",
          "Brand guidelines and logo files",
        ],
      },
      {
        id: "digital-design",
        title: "Digital and social graphics",
        description: "Give your posts, campaigns and customer touchpoints a consistent look.",
        points: [
          "Social post graphics and templates",
          "Digital ads and campaign graphics",
          "Website and email graphics",
        ],
      },
      {
        id: "print-design",
        title: "Print design",
        description: "Bring your brand into the places people meet you in person.",
        points: [
          "Business cards and stationery",
          "Flyers, menus and brochures",
          "Print-ready artwork",
        ],
      },
    ],
    faq: [
      {
        question: "Can you work with a logo we already have?",
        answer:
          "Yes. We can design new materials around your existing identity or scope a refresh if it needs to work better across digital and print.",
      },
      {
        question: "What files will we receive?",
        answer:
          "We agree the required formats when we quote. Depending on the project, that can include scalable logo files, digital exports and print-ready artwork.",
      },
      {
        question: "Can branding and a website be quoted together?",
        answer:
          "Yes. Tell us what you’re launching and we can scope the identity, artwork and website together.",
      },
    ],
    enquiry: "Tell us what you’re launching or refreshing and where the design will be used.",
  },
  seo: {
    title: "SEO services in Malta",
    headline: ["Get found for", "what you do."],
    introduction:
      "We help Malta and Gozo businesses improve how they appear in search, with local SEO, technical audits and ongoing optimisation.",
    description:
      "Local SEO, Google Business Profile support, technical SEO audits and ongoing search optimisation from Onyx Studio in Malta and Gozo.",
    offerings: [
      {
        id: "local-seo",
        title: "Local SEO",
        description:
          "Help people nearby find accurate information about your business and the services you offer.",
        points: [
          "Google Business Profile setup and optimisation",
          "Service and location page recommendations",
          "Consistent business details",
        ],
      },
      {
        id: "technical-seo",
        title: "Technical audits and fixes",
        description: "Find what is holding the site back and prioritise the fixes that matter.",
        points: [
          "Crawlability, indexing and redirects",
          "Page titles, headings and internal links",
          "Site performance and structured data",
        ],
      },
      {
        id: "ongoing-seo",
        title: "Ongoing optimisation",
        description:
          "Use search data to plan useful updates and track how visibility changes over time.",
        points: [
          "Search Console and performance reviews",
          "Content and page improvements",
          "Reporting on progress and next steps",
        ],
      },
    ],
    faq: [
      {
        question: "Can you work on a website someone else built?",
        answer:
          "Yes. Share the site you have and what you want to improve. We can audit it and agree which changes we can make directly or hand to your developer.",
      },
      {
        question: "Can I start with a one-off audit?",
        answer:
          "Yes. We can scope an audit with a prioritised list of fixes. If you want help implementing them or maintaining the site over time, we can quote for that too.",
      },
      {
        question: "How will I know what is improving?",
        answer:
          "We agree what to measure at the start. Depending on your goals, that can include search impressions, clicks, visibility for relevant queries and enquiries.",
      },
    ],
    enquiry:
      "Share your website, the services you want people to find and where your customers are based.",
  },
  "ai-automation": {
    title: "AI automation in Malta",
    headline: ["Keep enquiries", "moving."],
    introduction:
      "We build AI assistants and workflows that answer routine questions, collect details and follow up at the right time. Your team can approve replies and take over when an enquiry needs judgement.",
    description:
      "Onyx Studio builds AI assistants, workflow automation and connected tools for Malta businesses, including WhatsApp enquiries, quote follow-ups and booking reminders.",
    offerings: [
      {
        id: "ai-assistants",
        title: "AI assistants",
        description:
          "Help people get useful answers and give your team the context to handle the rest.",
        points: [
          "WhatsApp, website and email enquiries",
          "Answers grounded in your approved information",
          "Staff approval and handover for sensitive requests",
        ],
      },
      {
        id: "workflow-automation",
        title: "Workflow automation",
        description: "Give routine jobs a clear trigger, an owner and a next step.",
        points: [
          "Quote follow-ups and booking reminders",
          "Document requests and staff handovers",
          "Approval steps for customer-facing actions",
        ],
      },
      {
        id: "integrations",
        title: "Integrations within your workflow",
        description: "Connect the systems your team uses so information travels with an enquiry.",
        points: [
          "Calendars, email and WhatsApp Business",
          "Bookings, payment status and stock",
          "Data handoffs within your automation project",
        ],
      },
    ],
    faq: [
      {
        question: "Can we start by automating one job?",
        answer:
          "Yes. Pick a repetitive task such as collecting enquiry details or reminding customers about appointments. We can scope it first and expand once it works for your team.",
      },
      {
        question: "Who controls what the assistant sends?",
        answer:
          "You decide which answers can go out automatically and which need staff approval. We agree the sources, escalation rules and handover points before launch.",
      },
      {
        question: "Can it work with our existing tools?",
        answer:
          "We check which tools you use, what access each supports and how the data should move. We then quote the integrations needed for your workflow.",
      },
    ],
    enquiry:
      "Tell us what your team does on repeat, which tools they use and where a person should stay involved.",
  },
} as const satisfies Record<ServiceSlug, ServicePage>;

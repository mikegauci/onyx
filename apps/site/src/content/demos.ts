/**
 * Fictional demo conversations used by the interactive parts of the page. Names, prices and
 * places are illustrative only; no real customers or offers.
 */

export type Msg = { from: "customer" | "onyx" | "staff"; text: string };

/** Live approval queue in the hero: new enquiries arrive and move through these states. */
export const liveQueue = [
  { channel: "WhatsApp", text: "Is the blue Golf in Mosta still available?" },
  { channel: "Instagram", text: "Table for 6 in Valletta, Friday at 8?" },
  { channel: "Email", text: "Can you do a better price on the 2019 Yaris?" },
  { channel: "Web chat", text: "Do you deliver to Gozo, and how long does it take?" },
  { channel: "WhatsApp", text: "Can I view the Sliema apartment on Saturday?" },
  { channel: "Missed call", text: "Missed call · texted back with a booking link" },
  { channel: "Email", text: "Still need my FS3 for the tax return, which docs?" },
  { channel: "Instagram", text: "Any slots for a full valet this week?" },
] as const;

export const queueStates = ["Drafting", "Draft ready", "Approved", "Sent"] as const;

/** Playable system diagram: one scenario per channel. Outputs must match system.outputs. */
export const systemScenarios: Record<
  string,
  { message: string; checks: string[]; outputs: string[]; reply: string; needsApproval: boolean }
> = {
  WhatsApp: {
    message: "Hi, is the white Kia Picanto still for sale? Can I see it tomorrow?",
    checks: ["Found in stock: 2021 Kia Picanto, €11,950", "Tomorrow 10:00 and 15:30 free"],
    outputs: ["Stock & listings", "Bookings", "Customer records"],
    reply:
      "Hi! Yes, the 2021 Picanto is still available. I can book you tomorrow at 10:00 or 15:30 at our Mosta showroom. Which suits you?",
    needsApproval: false,
  },
  Email: {
    message: "Could you knock €1,000 off the Yaris if I pay cash this week?",
    checks: ["Price offer: outside auto-send policy", "Customer: 2 previous enquiries"],
    outputs: ["Customer records", "Staff approval"],
    reply:
      "Thanks for your offer on the Yaris. I've passed it to our sales team, who'll reply today.",
    needsApproval: true,
  },
  "Web chat": {
    message: "Do you have the black sofa in stock and can you deliver to Gozo?",
    checks: ["2 in stock at the Qormi warehouse", "Gozo delivery: Tuesdays and Fridays"],
    outputs: ["Stock & listings", "Bookings"],
    reply:
      "Yes, we have 2 in stock. We deliver to Gozo on Tuesdays and Fridays; shall I reserve one and book Friday?",
    needsApproval: false,
  },
  "Missed calls": {
    message: "Missed call from +356 79•• ••12 at 18:42",
    checks: ["Known customer: viewing booked last week", "Outside opening hours"],
    outputs: ["Customer records", "Bookings"],
    reply:
      "Sorry we missed your call! We're closed now, but you can pick a time to call back here, or reply with your question.",
    needsApproval: false,
  },
  Instagram: {
    message: "Can I book a table for 8 on Saturday and pay a deposit?",
    checks: ["Groups of 8+: deposit €10 per person", "Saturday 20:00 available"],
    outputs: ["Bookings", "Payments & deposits"],
    reply:
      "We'd love to have you! Saturday at 20:00 is free for 8. Here's a link to pay the €80 deposit and confirm.",
    needsApproval: false,
  },
};

/** Short sample conversation per industry card, keyed by industry slug. */
export const industryChats: Record<string, Msg[]> = {
  "car-dealerships": [
    { from: "customer", text: "Is the grey Tucson still available? What's the mileage?" },
    {
      from: "onyx",
      text: "Yes! 2020 Tucson, 48,000 km, full service history. Want to test drive it this week?",
    },
    { from: "customer", text: "Thursday after 5?" },
    { from: "onyx", text: "Booked for Thursday 17:30 at our Mosta showroom. See you then!" },
  ],
  "restaurants-hospitality": [
    { from: "customer", text: "Table for 4 tonight? One of us is coeliac." },
    {
      from: "onyx",
      text: "We have 20:30 free. Our menu marks gluten-free dishes and the kitchen can adapt most mains.",
    },
    { from: "customer", text: "Perfect, book it." },
    { from: "onyx", text: "Done: 4 people, 20:30, gluten-free noted for the kitchen." },
  ],
  "accounting-firms": [
    {
      from: "onyx",
      text: "Hi Maria, we still need your FS3 and last year's bank statements for your return.",
    },
    { from: "customer", text: "Attached the FS3. Statements tomorrow." },
    {
      from: "onyx",
      text: "Got the FS3, thank you. I'll remind you tomorrow about the statements.",
    },
  ],
  "hr-recruitment": [
    { from: "customer", text: "I applied for the receptionist role. Any update?" },
    {
      from: "onyx",
      text: "Thanks, Daniel. Your application passed screening. Can you interview on Wednesday at 10:00 or 14:00?",
    },
    { from: "customer", text: "14:00 works." },
    {
      from: "onyx",
      text: "Confirmed with the hiring team for Wednesday 14:00. Details are in your email.",
    },
  ],
  "property-agencies": [
    { from: "customer", text: "Looking for a 2-bed to rent in Sliema, up to €1,400." },
    {
      from: "onyx",
      text: "I have 3 matches. The closest is a 2-bed near the Ferries at €1,350. Want to view it?",
    },
    { from: "customer", text: "Saturday morning?" },
    { from: "onyx", text: "Booked Saturday 10:30 with Luke from our Sliema office." },
  ],
  marketplaces: [
    { from: "customer", text: "Is the listing still available and does the seller ship?" },
    {
      from: "onyx",
      text: "It's available. The seller collects in Birkirkara or ships within Malta for €8.",
    },
    { from: "customer", text: "Can I pay on collection?" },
    {
      from: "staff",
      text: "Approved by staff: yes, payment on collection is fine for this seller.",
    },
  ],
  "e-commerce": [
    { from: "customer", text: "Do these trainers come in 42? And when would they arrive?" },
    {
      from: "onyx",
      text: "Size 42 is in stock. Order before 14:00 and it ships today; delivery in Malta takes 1–2 days.",
    },
    { from: "customer", text: "Where's my last order?" },
    { from: "onyx", text: "Order #4127 is out for delivery and should reach you this afternoon." },
  ],
  "clinics-salons-studios": [
    { from: "customer", text: "Can I book a cut and colour next week?" },
    {
      from: "onyx",
      text: "Sure! Tuesday 11:00 or Thursday 16:00 with Rebecca. It takes about 2 hours.",
    },
    { from: "customer", text: "Thursday please." },
    { from: "onyx", text: "Booked. I'll send a reminder the day before." },
  ],
  "legal-professional": [
    { from: "customer", text: "I need help with a lease dispute with my landlord." },
    {
      from: "onyx",
      text: "I can arrange a consultation. Is this a residential or commercial lease, and is there a deadline?",
    },
    { from: "customer", text: "Residential, court date next month." },
    {
      from: "staff",
      text: "Flagged as urgent: a lawyer will call you today to arrange a meeting.",
    },
  ],
};

/** Small floating previews for the service rows, keyed by service title. */
export const servicePreviews: Record<string, "chat" | "checklist" | "browser" | "nodes"> = {
  "AI assistants": "chat",
  "Workflow automation": "checklist",
  "Websites that sell": "browser",
  Integrations: "nodes",
};

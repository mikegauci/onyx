export const enquiryFields = {
  name: 100,
  email: 254,
  business: 150,
  package: 20,
  brief: 3000,
} as const;

export type EnquiryValues = Record<keyof typeof enquiryFields, string>;

export const emptyEnquiry: EnquiryValues = {
  name: "",
  email: "",
  business: "",
  package: "",
  brief: "",
};

export type EnquiryState = {
  status: "idle" | "error" | "sent";
  message: string;
};

export const websiteDesignCampaign = {
  code: "website_design_300",
  label: "Facebook paid ad · Website design €300",
  message:
    "Hi Onyx Studio! I saw your Facebook ad for websites from €300 and would like to know more.",
} as const;

export function isWebsiteDesignCampaign(params: Pick<URLSearchParams, "get"> | null) {
  return (
    params?.get("utm_source") === "facebook" &&
    params.get("utm_medium") === "paid_social" &&
    params.get("utm_campaign") === websiteDesignCampaign.code
  );
}

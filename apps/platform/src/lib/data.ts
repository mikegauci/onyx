import "server-only";

import { cache } from "react";

import { withApi } from "./api-client";

/** Per-request cached loaders, so layouts and pages share one API call each. */
export const getMe = cache(() => withApi((api) => api.GET("/v1/me")));

/** The workspace's pilot controls (manual mode, feature switches). Every member may read them. */
export const getControls = cache((slug: string) =>
  withApi((api) => api.GET("/v1/w/{slug}/controls", { params: { path: { slug } } })),
);

export const getWorkspace = cache((slug: string) =>
  withApi((api) => api.GET("/v1/w/{slug}", { params: { path: { slug } } })),
);

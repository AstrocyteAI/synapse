import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import starlightSidebarTopics from "starlight-sidebar-topics";
import mermaid from "astro-mermaid";

const owner = process.env.GITHUB_REPOSITORY_OWNER || "AstrocyteAI";
const githubRepository = process.env.GITHUB_REPOSITORY;
const repositoryParts = githubRepository?.split("/").filter(Boolean) ?? [];
const repo =
  repositoryParts.length >= 2 ? repositoryParts[1] : repositoryParts[0];
const site = `https://${owner}.github.io`;
const base = repo ? `/${repo}/` : "/";
const defaultOgImage = new URL("logo.png", `${site}${base}`).href;

const topicItems = {
  design: [
    {
      label: "Architecture",
      items: [
        { label: "Architecture", link: "/design/architecture/" },
        { label: "Tech stack", link: "/design/tech-stack/" },
        { label: "Project structure", link: "/design/project-structure/" },
      ],
    },
    {
      label: "Features",
      items: [
        { label: "Chat", link: "/design/chat/" },
        { label: "Council engine", link: "/design/council-engine/" },
        { label: "Deliberation", link: "/design/deliberation/" },
        { label: "Workflows", link: "/design/workflows/" },
        { label: "Scheduling", link: "/design/scheduling/" },
        { label: "Notifications", link: "/design/notifications/" },
        { label: "Analytics", link: "/design/analytics/" },
      ],
    },
    {
      label: "Platform",
      items: [
        { label: "Multi-tenancy", link: "/design/multi-tenancy/" },
        { label: "RBAC", link: "/design/rbac/" },
        { label: "Integrations", link: "/design/integrations/" },
        { label: "Webhooks", link: "/design/webhooks/" },
        { label: "SDK", link: "/design/sdk/" },
        { label: "Templates", link: "/design/templates/" },
      ],
    },
    {
      label: "ADRs",
      collapsed: true,
      items: [],
    },
  ],
};

export default defineConfig({
  site,
  base,
  integrations: [
    mermaid({ autoTheme: true }),
    starlight({
      components: {
        Header: "./src/components/Header.astro",
        ThemeSelect: "./src/components/ThemeSelect.astro",
        Hero: "./src/components/Hero.astro",
      },
      title: "Synapse",
      favicon: "/favicon.svg",
      description:
        "Multi-human, multi-AI collaborative workspace built on Astrocyte.",
      plugins: [
        starlightSidebarTopics(
          [
            {
              id: "design",
              label: "Design",
              link: "/design/architecture/",
              icon: "document",
              items: topicItems.design,
            },
          ],
          {
            topics: {
              design: ["/", "/index"],
            },
          },
        ),
      ],
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/AstrocyteAI/synapse",
        },
      ],
      head: [
        {
          tag: "meta",
          attrs: { property: "og:image", content: defaultOgImage },
        },
        {
          tag: "meta",
          attrs: { property: "og:image:type", content: "image/png" },
        },
        {
          tag: "meta",
          attrs: { property: "og:image:alt", content: "Synapse — multi-human, multi-AI collaborative workspace" },
        },
        {
          tag: "meta",
          attrs: { name: "twitter:image", content: defaultOgImage },
        },
      ],
      customCss: ["./src/styles/custom.css"],
    }),
  ],
});

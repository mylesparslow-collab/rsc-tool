// Cloudflare Email Worker for rscrafters.com. See ../README.md.
import { EmailMessage } from "cloudflare:email";
import PostalMime from "postal-mime";
import { handleEmail } from "./handler.js";

export default {
  async email(message, env, ctx) {
    await handleEmail(message, env, { parse: (raw) => PostalMime.parse(raw), EmailMessage });
  },
};

# Let Nick see the app from his own computer (Tailscale)

Tailscale makes a private network between your Mac and Nick's devices. Nothing is put on the public internet.
Use this for the demo only. Keep it to demo data, not real client information.

## One time, on Myles's Mac
1. Install Tailscale (tailscale.com/download) and sign in.
2. In the Tailscale admin page (login.tailscale.com), open DNS and turn on **HTTPS Certificates**. This also lets the microphone buttons work for Nick.
3. Choose a PIN. Add this line to `~/RSC-demo/config.toml` (6 or more characters):
   `access_pin = "choose-a-pin"`
   With a PIN set, the app asks for it on every device, including yours.
4. Share the Mac with Nick: admin page > Machines > your Mac > ... > **Share**. Enter Nick's email. He installs Tailscale on his Mac, phone or iPad, signs in with that email, and accepts the share.

## Each time
1. Start the app: `cd ~/rsc-tool && RSC_HOME=~/RSC-demo .venv/bin/rsc serve --no-browser`
2. In a second Terminal window: `tailscale serve --bg 5151`. It prints an address like `https://your-mac.tail1234.ts.net`.
3. Keep the Mac awake: `caffeinate -d` in a third window.
4. Text Nick the address and the PIN. He opens it in his browser.

## Stop sharing
`tailscale serve reset`, then stop the app with Ctrl+C. Do not use `tailscale funnel`; that is public.

If Nick's page won't load, check that Tailscale shows "Connected" on both Macs, and that the share was accepted.

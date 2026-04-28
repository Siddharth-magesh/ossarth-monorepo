# OSSARTH — VirtualBox Deployment Guide

This document covers everything from setting up the Ubuntu 20.04 VM in Oracle VirtualBox
to having OSSARTH boot automatically when the VM starts. Follow every step in order.

> **Your Setup**
> - Hypervisor: Oracle VirtualBox (already installed)
> - ISO: `D:\ubuntu\ubuntu-20.04.6-desktop-amd64.iso` (already downloaded)
> - LLM: Ollama (local, primary) + Groq API (free tier, fallback)
> - No Anthropic / Claude API used anywhere

---

## What You Need Before Starting

| Requirement | Details |
|---|---|
| VirtualBox | Already installed on your Windows machine |
| Ubuntu ISO | `D:\ubuntu\ubuntu-20.04.6-desktop-amd64.iso` — already on disk |
| Free disk space | At least 25 GB on the drive where you store VMs |
| RAM | At least 6 GB free to allocate 4 GB to the VM |
| Groq API key | Free at https://console.groq.com — needed as LLM fallback |
| Ollama | Installed on your **Windows host** (not inside the VM) |

> **Important note on Ollama placement:**
> Ollama runs on your **Windows host** at `http://localhost:11434`.
> The Ubuntu VM connects to it over the VirtualBox host-only or NAT network.
> You do NOT need to install Ollama inside the VM.

---

## Part 1 — Create the VirtualBox Virtual Machine

### Step 1: Open VirtualBox and create a new VM

1. Open **Oracle VM VirtualBox Manager**
2. Click **"New"** (top toolbar)
3. Fill in the details:

```
Name:              OSSARTH
Machine Folder:    (leave default or pick any location with 25+ GB free)
Type:              Linux
Version:           Ubuntu (64-bit)
```

Click **Next**.

### Step 2: Set memory (RAM)

```
Memory size: 4096 MB  (4 GB)
```

4 GB is enough for Python + FastAPI + LLM inference context.
Click **Next**.

### Step 3: Create a virtual hard disk

- Select **"Create a virtual hard disk now"** → Click **Create**
- Hard disk file type: **VDI (VirtualBox Disk Image)** → Next
- Storage on physical hard disk: **Dynamically allocated** → Next
- File size: **25.00 GB** → Click **Create**

---

## Part 2 — Configure VM Settings Before First Boot

Before attaching the ISO and booting, adjust these settings.
Right-click your new VM → **Settings**.

### System tab

- **Motherboard** → Boot Order: Uncheck Floppy, keep Optical and Hard Disk
- **Processor** → CPUs: `2`  (gives OSSARTH two cores to work with)
- **Processor** → Enable PAE/NX: checked

### Display tab

- Video Memory: `128 MB`
- Graphics Controller: `VMSVGA`
- Do NOT enable 3D acceleration — Ubuntu 20.04 desktop can be unstable with it in VirtualBox

### Storage tab

1. Click the empty **optical drive** under "Controller: IDE"
2. Click the disc icon on the right → **"Choose a disk file..."**
3. Navigate to `D:\ubuntu\ubuntu-20.04.6-desktop-amd64.iso`
4. Click **Open**

You should see the ISO name appear next to the optical drive.

### Network tab

- **Adapter 1**: Attached to **NAT**
  - This gives the VM internet access through your Windows machine
  - The VM will get an IP in the `10.0.2.x` range internally

Click **OK** to save all settings.

---

## Part 3 — Install Ubuntu 20.04.6 Desktop

### Step 1: Start the VM

Double-click the VM in the VirtualBox Manager. The Ubuntu live environment will boot from the ISO (takes 30–60 seconds).

### Step 2: Choose install option

You will see the Ubuntu welcome screen with two buttons:
- **"Try Ubuntu"**
- **"Install Ubuntu"**

Click **"Install Ubuntu"**.

### Step 3: Keyboard layout

Select your keyboard layout (usually **English (US)**) → Continue.

### Step 4: Installation type options

- Updates and other software:
  - Select **"Normal installation"**
  - Check **"Download updates while installing Ubuntu"**
  - Check **"Install third-party software..."**
- Click **Continue**

### Step 5: Disk setup

- Select **"Erase disk and install Ubuntu"**
  *(This erases only the virtual disk — not your real Windows drive)*
- Click **"Install Now"** → **Continue** on the confirmation dialog

### Step 6: Timezone

Select your timezone (e.g. **Kolkata** for IST) → Continue.

### Step 7: User account

```
Your name:          OSSARTH
Computer's name:    ossarth
Username:           ossarth
Password:           ossarth123
Confirm password:   ossarth123
```

Select **"Log in automatically"** — this is important for the auto-boot demo setup.

Click **Continue**.

### Step 8: Wait for installation

Installation takes 10–25 minutes. When complete, click **"Restart Now"**.

When prompted to "remove the installation medium", press **Enter** —
VirtualBox removes the ISO automatically.

---

## Part 4 — First Boot Configuration

After reboot, Ubuntu desktop will appear (logged in automatically as `ossarth`).

### Step 1: Open a terminal

Press `Ctrl + Alt + T` or right-click the desktop → **"Open Terminal"**.

### Step 2: Update the system

```bash
sudo apt update && sudo apt upgrade -y
```

Enter password `ossarth123` when prompted. This takes 5–10 minutes.

### Step 3: Check Python version

Ubuntu 20.04 ships with Python 3.8. OSSARTH requires 3.10+. Install it:

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

Verify:
```bash
python3.11 --version
# Expected: Python 3.11.x
```

### Step 4: Install required system packages

```bash
sudo apt install -y \
  git \
  curl \
  wget \
  net-tools \
  htop \
  build-essential \
  python3-pip
```

### Step 5: Install VirtualBox Guest Additions (important for usability)

Guest Additions improve screen resolution, clipboard sharing, and folder sharing.

In the VirtualBox menu bar: **Devices → Insert Guest Additions CD image...**

Then in the terminal:
```bash
sudo apt install -y gcc make perl
sudo mount /dev/cdrom /mnt
sudo /mnt/VBoxLinuxAdditions.run
sudo reboot
```

After reboot, the VM window will resize properly and you can share clipboard
between Windows and the VM.

---

## Part 5 — Install Ollama on Windows Host (If Not Done)

Ollama runs on your **Windows machine**, not inside the VM. The VM connects to it over the network.

If Ollama is not installed yet:
1. Go to https://ollama.com/download and download the Windows installer
2. Run the installer
3. Open PowerShell and pull the model:

```powershell
ollama pull llama3.1:8b
```

4. Verify it is running:
```powershell
curl http://localhost:11434/api/tags
```

Should return JSON with model names.

> Ollama listens on `localhost:11434` by default.
> The VM needs to reach the **Windows host IP**, not `localhost`.

### Find your Windows host IP (visible from the VM)

In PowerShell on Windows:
```powershell
ipconfig
```

Look for **VirtualBox Host-Only Network** or the **Ethernet adapter** IP.
Typically `10.0.2.2` is the NAT gateway (your Windows host) as seen from inside the VM.

**Test from inside the VM:**
```bash
curl http://10.0.2.2:11434/api/tags
```

If this returns model data, Ollama is reachable from the VM.

> **If Ollama is not reachable:** Open Windows Defender Firewall →
> Allow an inbound rule for port `11434` from the VirtualBox subnet.

---

## Part 6 — Clone the OSSARTH Repository

Inside the VM terminal:

```bash
cd ~
git clone https://github.com/Siddharth-magesh/ossarth-monorepo.git ossarth
cd ossarth
```

Verify the structure:
```bash
ls -la
```

You should see: `mas_core/`, `mcp_tools/`, `kernel_sim/`, `dashboard/`,
`os_customization/`, `benchmarks/`, `requirements.txt`, `.env.example`, etc.

---

## Part 7 — Python Environment Setup

### Step 1: Create a virtual environment with Python 3.11

```bash
cd ~/ossarth
python3.11 -m venv venv
```

### Step 2: Activate it

```bash
source venv/bin/activate
```

Your prompt will change to `(venv) ossarth@ossarth:~$`.
This must be active every time you run OSSARTH.

### Step 3: Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs: `ollama`, `groq`, `fastapi`, `uvicorn`, `python-dotenv`, `pydantic`, `psutil`.

Verify:
```bash
pip list | grep -E "ollama|groq|fastapi|uvicorn|pydantic|psutil"
```

All six should appear.

---

## Part 8 — Configure Environment Variables

### Step 1: Create the `.env` file

```bash
cd ~/ossarth
cp .env.example .env
nano .env
```

### Step 2: Fill in the values

Edit the file to look like this:

```env
GROQ_API_KEY=gsk_your_actual_groq_key_here

# Provider: 'auto' = try Ollama first, fall back to Groq
# Change to 'groq' to force Groq-only (if Ollama unreachable from VM)
OSSARTH_LLM_PROVIDER=auto

# Point Ollama to the Windows host (10.0.2.2 = NAT gateway in VirtualBox)
OLLAMA_HOST=http://10.0.2.2:11434
OSSARTH_OLLAMA_MODEL=llama3.1:8b
OSSARTH_GROQ_MODEL=llama-3.1-8b-instant

OSSARTH_MAX_TOKENS=1000
OSSARTH_VERBOSE=false
OSSARTH_DASHBOARD_PORT=8000
OSSARTH_MAX_EXECUTION_STEPS=10
OSSARTH_PROCESS_TIMEOUT_SECONDS=10
OSSARTH_WORKSPACE=/home/ossarth/ossarth_workspace
OSSARTH_HISTORY_FILE=/home/ossarth/.ossarth_history
OSSARTH_STATE_FILE=/tmp/ossarth_state.json
```

**To save in nano:** `Ctrl+X` → `Y` → `Enter`

### Step 3: Get your Groq API key

1. Go to https://console.groq.com
2. Sign in (or create a free account)
3. Click **"API Keys"** in the left sidebar
4. Click **"Create API Key"**
5. Copy the key (starts with `gsk_`) and paste it into `.env`

### Step 4: Verify Groq connection

```bash
source venv/bin/activate
python3 -c "
from dotenv import load_dotenv
load_dotenv()
from mas_core import llm_client
status = llm_client.check_providers()
print('Ollama available:', status['ollama']['available'])
print('Groq key set:    ', status['groq']['key_set'])
"
```

Expected output:
```
Ollama available: True    # (or False if host IP isn't right yet)
Groq key set:     True
```

If Ollama shows False, set `OSSARTH_LLM_PROVIDER=groq` in `.env` to use Groq only.

---

## Part 9 — Create Required Directories

```bash
# Workspace for OSSARTH file operations
mkdir -p ~/ossarth_workspace

# Logs directory
mkdir -p ~/ossarth/logs

# Benchmark results directory
mkdir -p ~/ossarth/benchmarks/results

# Make the Linux launch script executable
chmod +x ~/ossarth/os_customization/launch.sh
```

---

## Part 10 — Test Each Layer Individually

Do not skip this. Debug one layer at a time.

### Test 1: Kernel simulation initialises

```bash
cd ~/ossarth && source venv/bin/activate
python3 -c "
from kernel_sim.resource_state import get_resource_state
s = get_resource_state()
d = s.to_dict()
print('CPU cores:', d['total_cpu_cores'])
print('RAM total:', d['total_ram_mb'], 'MB')
print('Keys:', list(d.keys())[:6])
print('Kernel sim: OK')
"
```

### Test 2: Tool registry loads

```bash
python3 -c "
from mcp_tools.tool_registry import ToolRegistry
r = ToolRegistry()
r.initialize()
print('Tools registered:', len(r._tools))
print('Tool registry: OK')
"
```

### Test 3: Filesystem MCP works

```bash
python3 -c "
from mcp_tools.filesystem_mcp import write_file, read_file
write_file('/home/ossarth/ossarth_workspace/test.txt', 'hello from ossarth')
content = read_file('/home/ossarth/ossarth_workspace/test.txt')
print('Read back:', content)
print('Filesystem MCP: OK')
"
```

### Test 4: Process listing works (psutil)

```bash
python3 -c "
from mcp_tools.process_mcp import list_processes
procs = list_processes()
print(f'Found {len(procs)} processes')
print('Top process:', procs[0]['name'] if procs else 'none')
print('Process MCP: OK')
"
```

### Test 5: LLM call works (tests Ollama or Groq)

```bash
python3 -c "
from dotenv import load_dotenv
load_dotenv()
from mas_core.intent_agent import IntentAgent
agent = IntentAgent(verbose=True)
result = agent.classify('list all running processes')
print('Task type:', result.task_type)
print('Intent Agent: OK')
"
```

Expected: `task_type: query_system`. If using Groq it takes ~1s; Ollama ~2–5s.

### Test 6: Full pipeline works

```bash
python3 -c "
from dotenv import load_dotenv
load_dotenv()
from mas_core.intent_agent import IntentAgent
from mas_core.orchestrator_agent import OrchestratorAgent
from mcp_tools.tool_registry import ToolRegistry
r = ToolRegistry(); r.initialize()
intent_agent = IntentAgent(verbose=False)
orchestrator = OrchestratorAgent(tool_registry=r, verbose=False)
intent = intent_agent.classify('list all running processes')
graph = orchestrator.plan(intent)
for step in graph.steps:
    print(f'  Step {step.step}: {step.tool}')
print('Full pipeline: OK')
"
```

### Test 7: Dashboard server starts

```bash
uvicorn dashboard.server:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health | python3 -m json.tool
kill %1
```

Expected: JSON response with `"status": "ok"`.

---

## Part 11 — Run the Full System

### Option A: Linux launch script (recommended)

```bash
cd ~/ossarth
source venv/bin/activate
./os_customization/launch.sh
```

This starts the dashboard in the background and the REPL in the foreground.
You will see the OSSARTH ASCII boot screen, then `OSSARTH >`.

### Option B: Start components manually (useful for debugging)

Open two terminals (`Ctrl+Alt+T` twice):

**Terminal 1 — Dashboard:**
```bash
cd ~/ossarth
source venv/bin/activate
uvicorn dashboard.server:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Daemon REPL:**
```bash
cd ~/ossarth
source venv/bin/activate
python3 -m mas_core.agent_runner
```

---

## Part 12 — Access the Dashboard From Windows

The dashboard runs on port 8000 inside the VM.
With NAT networking in VirtualBox, you need **port forwarding** to access it from Windows.

### Set up port forwarding in VirtualBox

1. With the VM **shut down**, open **Settings → Network → Adapter 1 (NAT)**
2. Click **"Advanced"** → **"Port Forwarding"**
3. Click the **+** icon to add a rule:

| Name | Protocol | Host IP | Host Port | Guest IP | Guest Port |
|---|---|---|---|---|---|
| OSSARTH-Dashboard | TCP | 127.0.0.1 | 8000 | | 8000 |
| OSSARTH-SSH | TCP | 127.0.0.1 | 2222 | | 22 |

4. Click **OK** → **OK**

Now start the VM. After OSSARTH is running, open your Windows browser:

```
http://localhost:8000
```

You should see the OSSARTH System Monitor dashboard with live CPU/RAM gauges
and the process table.

### SSH into the VM from Windows (much more comfortable than the VirtualBox console)

With the SSH port forwarding rule above:
```powershell
ssh ossarth@localhost -p 2222
```

Password: `ossarth123`

### If the dashboard does not load

**Check 1:** Is the server running inside the VM?
```bash
curl http://localhost:8000/health
```

**Check 2:** Is port forwarding set up correctly?
In VirtualBox with the VM running: **Machine → Settings → Network → Port Forwarding** — verify the rules are there.

**Check 3:** Is Ubuntu firewall blocking it?
```bash
sudo ufw status
# If active:
sudo ufw allow 8000/tcp
sudo ufw allow 22/tcp
```

---

## Part 13 — Configure Auto-Boot into OSSARTH (For Demo Day)

This makes the VM boot directly into the OSSARTH REPL on the console.
Ubuntu 20.04 Desktop auto-logs in (since you selected that during install).

### Step 1: Install OpenSSH server (so you can SSH in after auto-boot)

```bash
sudo apt install -y openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Step 2: Create the systemd service

```bash
sudo nano /etc/systemd/system/ossarth.service
```

Paste exactly:

```ini
[Unit]
Description=OSSARTH AI Daemon + Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ossarth
WorkingDirectory=/home/ossarth/ossarth
ExecStartPre=/bin/sleep 8
ExecStart=/bin/bash /home/ossarth/ossarth/os_customization/launch.sh
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=HOME=/home/ossarth
Environment=DISPLAY=:0

[Install]
WantedBy=graphical.target
```

Save with `Ctrl+X → Y → Enter`.

### Step 3: Enable the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable ossarth.service
```

### Step 4: Test the service

```bash
sudo systemctl start ossarth.service
sleep 10
sudo systemctl status ossarth.service
```

Expected: `Active: active (running)`.

If it shows `failed`, check logs:
```bash
sudo journalctl -u ossarth.service -n 50
```

### Step 5: Make the REPL appear on the desktop terminal at login

Add to `~/.bashrc`:
```bash
nano ~/.bashrc
```

Add at the very bottom:
```bash
# OSSARTH: launch REPL automatically on desktop login (not SSH)
if [ -z "$SSH_TTY" ] && [ "$TERM" != "dumb" ]; then
  if [ -f ~/ossarth/venv/bin/activate ]; then
    source ~/ossarth/venv/bin/activate
    cd ~/ossarth
    python3 -m mas_core.agent_runner
  fi
fi
```

Save and exit. Now when the VM boots and auto-logs in, a terminal showing
the OSSARTH REPL will appear automatically.

### Step 6: Reboot and verify

```bash
sudo reboot
```

After reboot (15–30 seconds), the Ubuntu desktop should appear with a terminal
running the OSSARTH boot screen and the `OSSARTH >` prompt.
Open your browser at `http://localhost:8000` to see the dashboard.

---

## Part 14 — VirtualBox Display Settings for the Demo

### Set a fixed resolution for the console

Inside the VM:
```bash
sudo nano /etc/default/grub
```

Find:
```
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
```

Change to:
```
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash video=1280x720"
```

Then:
```bash
sudo update-grub
sudo reboot
```

### Scale the VirtualBox window

- **View → Full Screen** (`Right Ctrl + F`) for the demo
- **View → Scaled Mode** (`Right Ctrl + C`) for a smaller window
- **View → Auto-resize Guest Display** — requires Guest Additions installed

### Split-screen demo layout (recommended)

- VirtualBox window: left half of screen → shows OSSARTH REPL
- Browser window: right half of screen → shows dashboard at `http://localhost:8000`

---

## Part 15 — Taking a Snapshot Before the Demo

Snapshots let you revert the VM instantly if something breaks.

With the VM **running** and everything working:

1. In VirtualBox menu bar: **Machine → Take Snapshot**
2. Name it: `OSSARTH Working - Pre-Demo`
3. Description: `All tests passing, Groq connected, dashboard accessible`
4. Click **OK**

To restore during the demo if something breaks:
- **Machine → Restore Snapshot** (or use the Snapshots panel)

---

## Part 16 — Quick Reference: Common Commands

### Start the full system

```bash
cd ~/ossarth && source venv/bin/activate && ./os_customization/launch.sh
```

### Check daemon status

```bash
sudo systemctl status ossarth.service
```

### View live logs

```bash
sudo journalctl -u ossarth.service -f
# Or:
tail -f ~/ossarth/logs/dashboard.log
```

### Restart everything

```bash
sudo systemctl restart ossarth.service
```

### Get the VM's IP address

```bash
ip addr show
# Look for inet 10.0.2.15 (NAT) or any other non-loopback address
```

### Clear workspace between demo runs

```bash
rm -rf ~/ossarth_workspace/*
rm -f /tmp/ossarth_state.json
```

### Pull latest code

```bash
cd ~/ossarth && git pull origin main
```

### Run all benchmarks

```bash
cd ~/ossarth && source venv/bin/activate
python3 benchmarks/latency_test.py
python3 benchmarks/accuracy_test.py
python3 benchmarks/consistency_test.py
python3 benchmarks/failure_recovery_test.py
python3 benchmarks/resource_overhead_test.py
python3 benchmarks/generate_report.py
cat benchmarks/results/summary.md
```

### Switch from Ollama to Groq-only

Edit `.env`:
```
OSSARTH_LLM_PROVIDER=groq
```

Restart the daemon. Groq is faster for demo purposes (< 1s responses).

---

## Part 17 — Troubleshooting

### ModuleNotFoundError when running any Python file

Virtual environment not active:
```bash
source ~/ossarth/venv/bin/activate
```

### Ollama not reachable from VM (`connection refused` on port 11434)

1. Confirm Ollama is running on Windows: open PowerShell → `curl http://localhost:11434/api/tags`
2. The VM reaches Windows host at `10.0.2.2` (VirtualBox NAT gateway)
3. Windows Firewall may be blocking. Add an inbound rule:
   - Open **Windows Defender Firewall → Advanced Settings**
   - **Inbound Rules → New Rule → Port → TCP 11434 → Allow**
4. As a fallback, set `OSSARTH_LLM_PROVIDER=groq` in `.env` — Groq always works over internet

### Groq key error (401 Unauthorized)

```bash
cat ~/ossarth/.env | grep GROQ
```

Verify the key starts with `gsk_`. If wrong, edit with `nano ~/ossarth/.env`.

### Dashboard shows no data / all zeros

State file missing — run any command in the REPL first, then reload the dashboard.
```bash
cat /tmp/ossarth_state.json
```

### Port 8000 not accessible from Windows browser

Check port forwarding is configured (Part 12) and the VM firewall:
```bash
sudo ufw status
sudo ufw allow 8000/tcp
```

### Python 3.11 not found after fresh clone

```bash
python3.11 --version
# If command not found, reinstall:
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update && sudo apt install -y python3.11 python3.11-venv
```

### VM has no internet after reboot (package installs fail)

```bash
ping 8.8.8.8
# If no response:
sudo dhclient enp0s3
# (interface may be enp0s3 instead of ens33 on VirtualBox)
```

Check interface name with: `ip link show`

### Auto-login opens desktop but no terminal appears

The `.bashrc` block runs only when a terminal is opened. Pin the **Terminal** app
to the Ubuntu taskbar and it will open on login. Or install `xterm` and add it
to **Startup Applications** (`gnome-session-properties`).

### VirtualBox console freezes or is laggy

This is normal for Ubuntu Desktop in VirtualBox without Guest Additions.
Install Guest Additions (Part 4 Step 5) and the display will be much smoother.
For production demo use, SSH in from Windows instead of using the VirtualBox console.

### REPL response takes > 30 seconds

Ollama on Windows may be cold-starting the model. Run one warm-up command first:
```
OSSARTH > list all running processes
```
Subsequent commands will be faster (model already loaded in memory).

---

## Summary: Boot-to-Demo Checklist

Run through this on demo day before presenting.

- [ ] VirtualBox VM is powered on and Ubuntu desktop appears
- [ ] Terminal opens and shows OSSARTH boot screen automatically
- [ ] `OSSARTH >` prompt is visible
- [ ] Run `show me all running processes` — verify it responds with process list
- [ ] Open browser on Windows at `http://localhost:8000` — verify dashboard loads
- [ ] Process table shows real processes (not empty)
- [ ] CPU and RAM gauges are updating every second
- [ ] Gauges change when a command is run in the REPL
- [ ] Groq fallback works: set `OSSARTH_LLM_PROVIDER=groq` and run a command
- [ ] VirtualBox snapshot taken (`Machine → Take Snapshot`)
- [ ] Split screen layout ready: VirtualBox console left, browser dashboard right

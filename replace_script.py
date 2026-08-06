import re

with open('templates/landing.html', 'r') as f:
    content = f.read()

old_button = '''<div data-aos="fade-up" data-aos-delay="600" class="flex flex-col items-center gap-2">
            <div class="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
                <a href="/login" class="bg-white text-black hover:bg-white/90 px-8 py-4 rounded-full font-bold tracking-wide transition shadow-[0_0_30px_rgba(255,255,255,0.2)] flex items-center justify-center gap-2">
                    <i data-lucide="log-in" class="w-5 h-5"></i> Dashboard Login
                </a>
                <a href="/invite" class="bg-white/10 text-white border border-white/20 hover:bg-white/20 px-8 py-4 rounded-full font-bold tracking-wide transition flex items-center justify-center gap-2">
                    <i data-lucide="plus" class="w-5 h-5"></i> Add to Server
                </a>
            </div>
            <p class="text-[10px] text-white/40 max-w-sm text-center mt-2 font-medium tracking-wide">
                Note: Logging in or Adding the bot will automatically join your account to the Project Nexus support server for updates.
            </p>
        </div>'''

new_buttons = '''<div data-aos="fade-up" data-aos-delay="600" class="flex flex-col items-center gap-2">
            <div class="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
                <a href="/invite" class="bg-white text-black hover:bg-white/90 px-8 py-4 rounded-full font-bold tracking-wide transition shadow-[0_0_30px_rgba(255,255,255,0.2)] flex items-center justify-center gap-2">
                    Get Started <i data-lucide="chevron-right" class="w-5 h-5"></i>
                </a>
                <a href="/bot-invite" class="bg-white/10 text-white border border-white/20 hover:bg-white/20 px-8 py-4 rounded-full font-bold tracking-wide transition flex items-center justify-center gap-2">
                    Add to Server <i data-lucide="plus" class="w-5 h-5"></i>
                </a>
            </div>
            <p class="text-[10px] text-white/40 max-w-sm text-center mt-2 font-medium tracking-wide">
                Note: Clicking 'Get Started' will connect your account and automatically add you to the Project Nexus support server.
            </p>
        </div>'''

content = content.replace(old_button, new_buttons)

with open('templates/landing.html', 'w') as f:
    f.write(content)

import os, subprocess
JDK = r'E:\jdk11'; SDK = r'E:\AndroidSDK'
sm = os.path.join(SDK, 'cmdline-tools', 'latest', 'bin', 'sdkmanager.bat')
e = os.environ.copy(); e['JAVA_HOME'] = JDK
e['PATH'] = os.path.join(JDK, 'bin') + ';' + os.path.join(SDK, 'cmdline-tools', 'latest', 'bin') + ';' + e.get('PATH', '')
p = subprocess.run('cmd.exe /c "%s" --version' % sm, env=e, capture_output=True, text=True, shell=True, timeout=120)
print('rc=', p.returncode)
print('STDOUT:', p.stdout.strip()[-400:])
print('STDERR:', p.stderr.strip()[-600:])

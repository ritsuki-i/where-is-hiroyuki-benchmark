"""Verify the two direct-model requests use the documented task and images."""
import base64
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import server


class DirectProtocolTests(unittest.TestCase):
    def test_jev_and_opus_receive_shared_prompt_and_prepared_images(self):
        payloads={}
        class Response:
            def __enter__(self):
                payload={'model':server.MODEL,'answers':{'target':{'box':{'left':0.1,'top':0.1,'right':0.2,'bottom':0.2}}}}
                return io.BytesIO(json.dumps(payload).encode())
            def __exit__(self,*args): pass

        def urlopen(request,timeout):
            payloads['jev']=json.loads(request.data)
            return Response()

        def run(args,**kwargs):
            if args[1:3]==['auth','status']:
                output={'loggedIn':True,'authMethod':'claude.ai','subscriptionType':'pro'}
            else:
                workdir=Path(kwargs['cwd'])
                self.assertEqual({p.name for p in workdir.iterdir()},{'reference.jpg','scene.jpg'})
                payloads['opus_reference']=(workdir/'reference.jpg').read_bytes()
                payloads['opus_scene']=(workdir/'scene.jpg').read_bytes()
                payloads['opus_prompt']=args[args.index('-p')+1]
                self.assertIn('--restricted',args)
                self.assertIn('--strict-mcp-config',args)
                self.assertEqual(args[args.index('--tools')+1],'Read')
                self.assertEqual(args[args.index('--system-prompt')+1],server.PROTOCOL['models']['Opus']['system_prompt'])
                output={'result':'{"box":[0.1,0.1,0.2,0.2]}',
                        'modelUsage':{'claude-opus-5-5':{}}}
            return subprocess.CompletedProcess(args,0,json.dumps(output),'')

        with patch.object(server,'read_key',return_value='test-token'),patch.object(server.urllib.request,'urlopen',side_effect=urlopen):
            server.run_jev(0)
        with patch.object(server.shutil,'which',return_value='claude.cmd'),patch.object(server.subprocess,'run',side_effect=run):
            server.run_opus(0)
        jev=payloads['jev']
        self.assertIn(server.PROTOCOL['prompt'],jev['questions']['target']['instructions'])
        self.assertIn(server.PROTOCOL['prompt'],payloads['opus_prompt'])
        ref=jev['state']['reference']
        scene=jev['state']['scene']
        self.assertEqual(base64.b64decode(jev['assets'][ref]['data_base64']),payloads['opus_reference'])
        self.assertEqual(base64.b64decode(jev['assets'][scene]['data_base64']),payloads['opus_scene'])


if __name__=='__main__':
    unittest.main()

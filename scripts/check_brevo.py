import os
from dotenv import load_dotenv
load_dotenv()
print('HAS=', bool(os.getenv('BREVO_API_KEY')))
print('VAL=', (os.getenv('BREVO_API_KEY') or '')[:16])

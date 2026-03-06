import asyncio
import json
import unittest
from io import BytesIO
from pathlib import Path

from starlette.datastructures import UploadFile

from scheduler.app import schedule


class AppTests(unittest.TestCase):
    def test_schedule_endpoint_section_offerings_mode(self):
        requests_bytes = Path('input/new/ScheduleRequests.export.txt').read_bytes()
        offerings_bytes = Path('input/new/Sem 1 sample sked export with phases.txt').read_bytes()

        requests_file = UploadFile(filename='ScheduleRequests.export.txt', file=BytesIO(requests_bytes))
        offerings_file = UploadFile(filename='Sem 1 sample sked export with phases.txt', file=BytesIO(offerings_bytes))

        response = asyncio.run(
            schedule(requests_export=requests_file, section_offerings=offerings_file)
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertIn('schedulecc_csv', payload)
        self.assertIn('dropped_by_reason_csv', payload)
        self.assertIn('summary', payload)
        self.assertIn('SCHEDULECC.Course_Number', payload['schedulecc_csv'])
        self.assertIn('reason', payload['dropped_by_reason_csv'])


if __name__ == '__main__':
    unittest.main()

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL;

const FORM_DATA = {
  år: '2024',
  månad: '06',
  dag: '15',
  prisklass: 'SE3',
};

export const options = {
  stages: [
    { duration: '30s', target: 20 },
    { duration: '30s', target: 50 },
    { duration: '2m', target: 50 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const res = http.post(`${BASE_URL}/api`, FORM_DATA);

  check(res, {
    'status är 200': (r) => r.status === 200,
    'svaret innehåller elpris-tabell': (r) => r.body.includes('Elpriset för'),
  });

  sleep(0.5);
}
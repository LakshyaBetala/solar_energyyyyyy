# KPI 1 audit test log

Run 19 Nov 2026 20:31, `tests/k1_audit.py`. 119 of 119 cases pass.

| # | ID | Area | Input | Expected | Actual | Result |
|---|---|---|---|---|---|---|
| 1 | D01 | create customer | 12 customers added at the same moment | 12 x 200, 12 different IDs | [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200] | PASS |
| 2 | D02 | details: consumer no. | 'abc' over a saved number | 400; the saved number kept | (400, '170055509871') | PASS |
| 3 | D11 | details: consumer no. | '123456789' | 400 | (400, 'the consumer number on an MSEDCL bill has 12 digits;  | PASS |
| 4 | D11 | details: consumer no. | '1234567890123' | 400 | (400, 'the consumer number on an MSEDCL bill has 12 digits;  | PASS |
| 5 | D11 | details: consumer no. | '000000000000' | 400 | (400, 'that consumer number repeats one digit; check it on t | PASS |
| 6 | D11 | details: consumer no. | '1700-5550-9871' (hyphens) | accepted as 170055509871 | 200 | PASS |
| 7 | D03 | registration page: cost | '2,50,000' | saved as 250000 | (200, '250000') | PASS |
| 8 | D03 | closeout page: cost | '2,50,000' | saved as 250000 | (200, '250000') | PASS |
| 9 | D03 | registration page: cost | '143000' | saved as 143000 | (200, '143000') | PASS |
| 10 | D03 | closeout page: cost | '143000' | saved as 143000 | (200, '143000') | PASS |
| 11 | D03 | registration page: cost | '₹2,00,000' | saved as 200000 | (200, '200000') | PASS |
| 12 | D03 | closeout page: cost | '₹2,00,000' | saved as 200000 | (200, '200000') | PASS |
| 13 | D03 | registration page: cost | 'Rs 300000' | saved as 300000 | (200, '300000') | PASS |
| 14 | D03 | closeout page: cost | 'Rs 300000' | saved as 300000 | (200, '300000') | PASS |
| 15 | D03 | registration page: cost | 'Rs 1.5 lakh' | 400, nothing saved | (400, 'pick the installation cost from the list: 125,000, 14 | PASS |
| 16 | D03 | closeout page: cost | 'Rs 1.5 lakh' | 400, nothing saved | (400, 'pick the installation cost from the list: 125,000, 14 | PASS |
| 17 | D03 | registration page: cost | '-250000' | 400, nothing saved | (400, 'pick the installation cost from the list: 125,000, 14 | PASS |
| 18 | D03 | closeout page: cost | '-250000' | 400, nothing saved | (400, 'pick the installation cost from the list: 125,000, 14 | PASS |
| 19 | D03 | registration page: cost | '0' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 20 | D03 | closeout page: cost | '0' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 21 | D03 | registration page: cost | '999999999999' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 22 | D03 | closeout page: cost | '999999999999' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 23 | D03 | registration page: cost | 'abc' | 400, nothing saved | (400, 'pick the installation cost from the list: 125,000, 14 | PASS |
| 24 | D03 | closeout page: cost | 'abc' | 400, nothing saved | (400, 'pick the installation cost from the list: 125,000, 14 | PASS |
| 25 | D03 | registration page: cost | '250000.50' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 26 | D03 | closeout page: cost | '250000.50' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 27 | D03 | registration page: cost | '210000' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 28 | D03 | closeout page: cost | '210000' | 400, nothing saved | (400, 'the installation cost must be one of: 125,000, 143,00 | PASS |
| 29 | D09 | details: name | '123' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 30 | D09 | details: name | '@@@ ###' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 31 | D09 | details: name | 'Priya1234' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 32 | D09 | details: name | '<script>x</script>' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 33 | D09 | details: name | 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' | 400 | (400, "the customer's name must be 3 to 80 characters") | PASS |
| 34 | D09/R7 | details: name | 'A. K. Sharma' | accepted | (200, '') | PASS |
| 35 | D09/R7 | details: name | 'D’Souza Maria' | accepted | (200, '') | PASS |
| 36 | D09/R7 | details: name | "Mary D'Souza" | accepted | (200, '') | PASS |
| 37 | D09/R7 | details: name | 'प्रिया कुलकर्णी' | accepted | (200, '') | PASS |
| 38 | D09/R7 | details: name | 'कऱ्हाडे\u200d संजय' | accepted | (200, '') | PASS |
| 39 | D09/R7 | details: name | 'Rajendra Kumar Venkataraman Subramaniam Iyer' | accepted | (200, '') | PASS |
| 40 | D10 | details: Aadhaar | a valid full number 9999 4105 7058 | 200; only 7058 kept | 7058 | PASS |
| 41 | D10 | details: Aadhaar | '9999 4105 7050' | 400 | (400, 'this Aadhaar number does not pass the check-digit tes | PASS |
| 42 | D10 | details: Aadhaar | 'abcd' | 400 | (400, 'enter only the last 4 digits of the Aadhaar, e.g. 447 | PASS |
| 43 | D10 | details: Aadhaar | '12' | 400 | (400, 'enter only the last 4 digits of the Aadhaar, e.g. 447 | PASS |
| 44 | D10 | details: Aadhaar | '99999999' | 400 | (400, 'enter only the last 4 digits of the Aadhaar, e.g. 447 | PASS |
| 45 | D10 | details: Aadhaar | '0123 4567 8901' | 400 | (400, 'an Aadhaar number never starts with 0 or 1; check it  | PASS |
| 46 | R1 | close-out page: Aadhaar | full number in 'last 4 digits only' | only 7058 stored; the full number nowhere | (200, '7058') | PASS |
| 47 | R1 | audit trail | after the Aadhaar was typed | the full number is not in the audit trail | checked | PASS |
| 48 | D12 | registration page: mobile | 'abcdefghij' | 400 | (400, 'the mobile number has digits only; it has none') | PASS |
| 49 | D12 | closeout page: mobile | 'abcdefghij' | 400 | (400, 'the mobile number has digits only; it has none') | PASS |
| 50 | D12 | registration page: mobile | '12345' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 51 | D12 | closeout page: mobile | '12345' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 52 | D12 | registration page: mobile | '5028144599' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 53 | D12 | closeout page: mobile | '5028144599' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 54 | M1 | details: mobile | '+91 90281 44599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 55 | M1 | details: mobile | '+91-90281-44599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 56 | M1 | details: mobile | '090281 44599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 57 | M1 | details: mobile | '9028144599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 58 | M1 | dashboard boxes | maxlength of the mobile boxes | room for '+91 90281 44599' (15) | [16, 16] | PASS |
| 59 | D13 | wrong-typed input | /api/registration/SS-2063 {'name': 123} | 400, never 500 | 400 | PASS |
| 60 | D13 | wrong-typed input | /api/registration/SS-2063 {'kw': [1]} | 400, never 500 | 400 | PASS |
| 61 | D13 | wrong-typed input | /api/registration/SS-2063 {'mobile': {'a': 1}} | 400, never 500 | 400 | PASS |
| 62 | D13 | wrong-typed input | /api/closeout/SS-2063 {'mobile': [1]} | 400, never 500 | 400 | PASS |
| 63 | D13 | wrong-typed input | /api/closeout/SS-2063 {'aadhaar_last4': {'x': 1}} | 400, never 500 | 400 | PASS |
| 64 | D13 | wrong-typed input | /api/customers {'name': ['a']} | 400, never 500 | 400 | PASS |
| 65 | D13 | wrong-typed input | login with a number as username | 400 or 401, never 500 | 401 | PASS |
| 66 | M2 | application no. | a Maharashtra number one digit short | 400 | (400, 'a Maharashtra application number ends in 8 digits, li | PASS |
| 67 | D04 | application no. | first number NP-MHSED26-35226411 | saved | (200, '') | PASS |
| 68 | D04 | application no. | an operator registers again with another number | 400; the first kept | 400 | PASS |
| 69 | R6 | application no. | a supervisor replaces it with a number already on another customer | 400 and no 'Replaced' audit row | (400, 0) | PASS |
| 70 | R6 | application no. | a supervisor replaces it correctly | 200 and one audit row | (200, 1) | PASS |
| 71 | D05 | step order | register a customer with no documents (typed by hand) | 400 | (400, 'cannot register: upload the bill and Aadhaar and chec | PASS |
| 72 | D05 | step order | accept before registering | 400 | 400 | PASS |
| 73 | D05 | step order | send the agreement before the vendor accepted (Registration) | 400 | (400, 'cannot send the agreement: accept the customer in the | PASS |
| 74 | R8 | step order | send the agreement before the vendor accepted (Close-out route) | 400 | (400, 'not ready to send: Vendor-consumer agreement (Missing | PASS |
| 75 | R4 | co-pilot | number read off the portal for a customer Solara thought not ready | kept (the portal registered them) | (200, '') | PASS |
| 76 | R2 | extraction | confirm the bill's mobile when the owner typed another | the typed mobile (the OTP phone) kept | (200, '9890022222') | PASS |
| 77 | R3 | extraction | confirm the consumer number with 'abc' | 400 | (400, 'the consumer number has digits only (spaces and hyphe | PASS |
| 78 | R3 | extraction | confirm it as '1700 5550 1234' | stored as 170055501234 | (200, '') | PASS |
| 79 | R11 | extraction | a hand correction to the bill, then a new bill uploaded | the new bill's reading wins | LT-I RES | PASS |
| 80 | R12 | registration page | sanctioned load read as '3.5 kW approx.' | the page loads (no 500) | 200 | PASS |
| 81 | P3 | details | a customer with no email | not missing: the portal's email is optional (7 Nov recording) | ['consumer number', 'mobile', 'proposed capacity (kW)'] | PASS |
| 82 | D14 | e-sign page | ?error= with crafted text | the text is not shown | checked | PASS |
| 83 | M6 | e-sign page | wrong last-4 digits | told in English and Marathi, with the tries left | checked | PASS |
| 84 | R10 | e-sign page | a 9000x9000 'signature' (20 KB) | refused in under 2 s, server keeps serving | 0.02s | PASS |
| 85 | R7 | e-sign page | the customer signs as 'D’Souza Priya' (curly apostrophe) | signed | signed | PASS |
| 86 | R9 | e-sign evidence | a link sent before copies were kept is signed | a copy is kept at signing; the agreement verifies | verified | PASS |
| 87 | D15 | dashboard | GET /favicon.ico | no 404 | checked | PASS |
| 88 | P1 | co-pilot | manifest hosts | consumer. and vendor.pmsuryaghar.gov.in included | ['https://rts.mahadiscom.in/RoofTopSolarVendor/*', 'https:// | PASS |
| 89 | P2 | dashboard links | live 'Open customer registration' / 'Open vendor login' | the real login pages | {'pmsg': 'https://consumer.pmsuryaghar.gov.in/consumer/#/log | PASS |
| 90 | P4 | rules | valid.app_no on 8-digit MH numbers | NP-MHSED26-12345678 accepted | checked | PASS |
| 91 | E1 | details: district | the old name 'Ahmednagar' | saved as the portal's 'Ahilyanagar' | Ahilyanagar | PASS |
| 92 | E1 | details: district | 'Atlantis' | 400; not a district on the portal | (400, 'Atlantis is not a Maharashtra district on the portal; | PASS |
| 93 | E1 | extraction: district | Aadhaar QR says 'Aurangabad' | stored as 'Chhatrapati Sambhajinagar' | checked | PASS |
| 94 | E1 | dashboard | the district list | the portal's 36 Maharashtra districts | 36 | PASS |
| 95 | E2 | customer link | the customer opens it | 200, greets them by first name, WhatsApp to their own number | 200 | PASS |
| 96 | E2 | customer link | a viewer asks for a link | 403 | checked | PASS |
| 97 | E2 | customer link | the customer sends the bill PDF | stored, read like an owner upload, and the page says received | (303, ['address', 'amount', 'avg_units', 'bill_mobile']) | PASS |
| 98 | E2 | customer link | the page after the upload | the bill ticked, the Aadhaar asked for next; never the bill's contents | checked | PASS |
| 99 | E2 | customer link | a document kind the link does not ask for | refused | /up/VHNlhJ1yINRXHUgqtkzZgsRV?err=type | PASS |
| 100 | E2 | customer link | a wrong email | refused, nothing saved | /up/VHNlhJ1yINRXHUgqtkzZgsRV?err=email | PASS |
| 101 | E2 | customer link | the customer types their email | saved on the record | link.c@example.com | PASS |
| 102 | L2 | customer link | bill and email sent, Aadhaar not yet | one thing asked: the Aadhaar, step 2 of 3; not 'All done' | checked | PASS |
| 103 | L1 | customer link | a link made while Solara runs on this computer | flagged: it will not open on the customer's phone | True | PASS |
| 104 | L1 | customer link | SOLARA_PUBLIC_URL set to the internet address | links use that address | https://solara.example.in/up/abc | PASS |
| 105 | L3 | dashboard | the dashboard's script file | the browser checks for a newer copy on every load | checked | PASS |
| 106 | E2 | customer link | a made-up link | 404 | checked | PASS |
| 107 | E2 | customer link | the 31st file on one link | refused; the owner sends a new link | /up/VHNlhJ1yINRXHUgqtkzZgsRV?err=many | PASS |
| 108 | E2 | customer link | after 7 days | 410, expired | checked | PASS |
| 109 | E3 | co-pilot: My Application | a status Solara does not know, and a number on no customer | nothing marked; the status is reported | {'ok': True, 'updated': [], 'unknown': ['Something new (Pend | PASS |
| 110 | E3 | co-pilot: My Application | the customer listed as 'Upload Agreement (Pending)' | marked accepted in Solara, no click | [{'id': 'SS-2070', 'name': 'List Customer', 'what': 'accepte | PASS |
| 111 | E3 | co-pilot: My Application | the portal is past the agreement, Solara has no signed one | not marked uploaded; the gap is shown | {'ok': True, 'updated': [], 'unknown': [], 'problems': [{'id | PASS |
| 112 | M3 | details form | the email box | not marked as needed: the portal's email is optional | Email | PASS |
| 113 | M4 | details form | type 3 into the highlighted capacity box | the 'missing' highlight goes as soon as it has a value | (True, False) | PASS |
| 114 | M5 | details form | type 200000 as the cost | read back as Rs 2,00,000 (a missed zero shows) | Rs 2,00,000 | PASS |
| 115 | U7 | Registration screen | a new customer (next step: documents) | Documents first and open; the portal section folded | {'first': 'regDocs', 'open': True, 'portal': False, 'body':  | PASS |
| 116 | U8 | Registration screen | text size and labels | body 15px; labels at least 13px, not in capitals | {'first': 'regDocs', 'open': True, 'portal': False, 'body':  | PASS |
| 117 | U9 | Registration screen | open the folded portal section, then the screen redraws | it stays open | [True, True] | PASS |
| 118 | E4 | Registration screen | tap the 3 kW button | capacity filled with 3; the button shows it is picked | ['3', '3 kW'] | PASS |
| 119 | E4 | Registration screen | the district box | a list of the portal's districts, not a text box | SELECT:37 | PASS |

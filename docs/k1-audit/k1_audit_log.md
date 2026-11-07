# KPI 1 audit test log

Run 07 Nov 2026 14:13, `tests/k1_audit.py`. 111 of 111 cases pass.

| # | ID | Area | Input | Expected | Actual | Result |
|---|---|---|---|---|---|---|
| 1 | D01 | create customer | 12 customers added at the same moment | 12 x 200, 12 different IDs | [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200] | PASS |
| 2 | D02 | details: consumer no. | 'abc' over a saved number | 400; the saved number kept | (400, '170055509871') | PASS |
| 3 | D11 | details: consumer no. | '123456789' | 400 | (400, 'the consumer number on an MSEDCL bill has 12 digits;  | PASS |
| 4 | D11 | details: consumer no. | '1234567890123' | 400 | (400, 'the consumer number on an MSEDCL bill has 12 digits;  | PASS |
| 5 | D11 | details: consumer no. | '000000000000' | 400 | (400, 'that consumer number repeats one digit; check it on t | PASS |
| 6 | D11 | details: consumer no. | '1700-5550-9871' (hyphens) | accepted as 170055509871 | 200 | PASS |
| 7 | D03 | registration page: cost | '250000.50' | saved as 250000.50 | (200, '250000.50') | PASS |
| 8 | D03 | closeout page: cost | '250000.50' | saved as 250000.50 | (200, '250000.50') | PASS |
| 9 | D03 | registration page: cost | '2,50,000.75' | saved as 250000.75 | (200, '250000.75') | PASS |
| 10 | D03 | closeout page: cost | '2,50,000.75' | saved as 250000.75 | (200, '250000.75') | PASS |
| 11 | D03 | registration page: cost | '₹2,10,000' | saved as 210000 | (200, '210000') | PASS |
| 12 | D03 | closeout page: cost | '₹2,10,000' | saved as 210000 | (200, '210000') | PASS |
| 13 | D03 | registration page: cost | 'Rs 285000' | saved as 285000 | (200, '285000') | PASS |
| 14 | D03 | closeout page: cost | 'Rs 285000' | saved as 285000 | (200, '285000') | PASS |
| 15 | D03 | registration page: cost | 'Rs 1.5 lakh' | 400, nothing saved | (400, 'the installation cost is an amount in rupees, like 28 | PASS |
| 16 | D03 | closeout page: cost | 'Rs 1.5 lakh' | 400, nothing saved | (400, 'the installation cost is an amount in rupees, like 28 | PASS |
| 17 | D03 | registration page: cost | '-250000' | 400, nothing saved | (400, 'the installation cost is an amount in rupees, like 28 | PASS |
| 18 | D03 | closeout page: cost | '-250000' | 400, nothing saved | (400, 'the installation cost is an amount in rupees, like 28 | PASS |
| 19 | D03 | registration page: cost | '0' | 400, nothing saved | (400, 'the installation cost should be between Rs 10,000 and | PASS |
| 20 | D03 | closeout page: cost | '0' | 400, nothing saved | (400, 'the installation cost should be between Rs 10,000 and | PASS |
| 21 | D03 | registration page: cost | '999999999999' | 400, nothing saved | (400, 'the installation cost should be between Rs 10,000 and | PASS |
| 22 | D03 | closeout page: cost | '999999999999' | 400, nothing saved | (400, 'the installation cost should be between Rs 10,000 and | PASS |
| 23 | D03 | registration page: cost | 'abc' | 400, nothing saved | (400, 'the installation cost is an amount in rupees, like 28 | PASS |
| 24 | D03 | closeout page: cost | 'abc' | 400, nothing saved | (400, 'the installation cost is an amount in rupees, like 28 | PASS |
| 25 | D09 | details: name | '123' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 26 | D09 | details: name | '@@@ ###' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 27 | D09 | details: name | 'Priya1234' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 28 | D09 | details: name | '<script>x</script>' | 400 | (400, "the customer's name: use letters and spaces (a full s | PASS |
| 29 | D09 | details: name | 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' | 400 | (400, "the customer's name must be 3 to 80 characters") | PASS |
| 30 | D09/R7 | details: name | 'A. K. Sharma' | accepted | (200, '') | PASS |
| 31 | D09/R7 | details: name | 'D’Souza Maria' | accepted | (200, '') | PASS |
| 32 | D09/R7 | details: name | "Mary D'Souza" | accepted | (200, '') | PASS |
| 33 | D09/R7 | details: name | 'प्रिया कुलकर्णी' | accepted | (200, '') | PASS |
| 34 | D09/R7 | details: name | 'कऱ्हाडे\u200d संजय' | accepted | (200, '') | PASS |
| 35 | D09/R7 | details: name | 'Rajendra Kumar Venkataraman Subramaniam Iyer' | accepted | (200, '') | PASS |
| 36 | D10 | details: Aadhaar | a valid full number 9999 4105 7058 | 200; only 7058 kept | 7058 | PASS |
| 37 | D10 | details: Aadhaar | '9999 4105 7050' | 400 | (400, 'this Aadhaar number does not pass the check-digit tes | PASS |
| 38 | D10 | details: Aadhaar | 'abcd' | 400 | (400, 'enter only the last 4 digits of the Aadhaar, e.g. 447 | PASS |
| 39 | D10 | details: Aadhaar | '12' | 400 | (400, 'enter only the last 4 digits of the Aadhaar, e.g. 447 | PASS |
| 40 | D10 | details: Aadhaar | '99999999' | 400 | (400, 'enter only the last 4 digits of the Aadhaar, e.g. 447 | PASS |
| 41 | D10 | details: Aadhaar | '0123 4567 8901' | 400 | (400, 'an Aadhaar number never starts with 0 or 1; check it  | PASS |
| 42 | R1 | close-out page: Aadhaar | full number in 'last 4 digits only' | only 7058 stored; the full number nowhere | (200, '7058') | PASS |
| 43 | R1 | audit trail | after the Aadhaar was typed | the full number is not in the audit trail | checked | PASS |
| 44 | D12 | registration page: mobile | 'abcdefghij' | 400 | (400, 'the mobile number has digits only; it has none') | PASS |
| 45 | D12 | closeout page: mobile | 'abcdefghij' | 400 | (400, 'the mobile number has digits only; it has none') | PASS |
| 46 | D12 | registration page: mobile | '12345' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 47 | D12 | closeout page: mobile | '12345' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 48 | D12 | registration page: mobile | '5028144599' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 49 | D12 | closeout page: mobile | '5028144599' | 400 | (400, 'the mobile number has 10 digits and starts with 6, 7, | PASS |
| 50 | M1 | details: mobile | '+91 90281 44599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 51 | M1 | details: mobile | '+91-90281-44599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 52 | M1 | details: mobile | '090281 44599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 53 | M1 | details: mobile | '9028144599' | accepted as 9028144599 | (200, '9028144599') | PASS |
| 54 | M1 | dashboard boxes | maxlength of the mobile boxes | room for '+91 90281 44599' (15) | [16, 16] | PASS |
| 55 | D13 | wrong-typed input | /api/registration/SS-2063 {'name': 123} | 400, never 500 | 400 | PASS |
| 56 | D13 | wrong-typed input | /api/registration/SS-2063 {'kw': [1]} | 400, never 500 | 400 | PASS |
| 57 | D13 | wrong-typed input | /api/registration/SS-2063 {'mobile': {'a': 1}} | 400, never 500 | 400 | PASS |
| 58 | D13 | wrong-typed input | /api/closeout/SS-2063 {'mobile': [1]} | 400, never 500 | 400 | PASS |
| 59 | D13 | wrong-typed input | /api/closeout/SS-2063 {'aadhaar_last4': {'x': 1}} | 400, never 500 | 400 | PASS |
| 60 | D13 | wrong-typed input | /api/customers {'name': ['a']} | 400, never 500 | 400 | PASS |
| 61 | D13 | wrong-typed input | login with a number as username | 400 or 401, never 500 | 401 | PASS |
| 62 | M2 | application no. | a Maharashtra number one digit short | 400 | (400, 'a Maharashtra application number ends in 8 digits, li | PASS |
| 63 | D04 | application no. | first number NP-MHSED26-35226411 | saved | (200, '') | PASS |
| 64 | D04 | application no. | an operator registers again with another number | 400; the first kept | 400 | PASS |
| 65 | R6 | application no. | a supervisor replaces it with a number already on another customer | 400 and no 'Replaced' audit row | (400, 0) | PASS |
| 66 | R6 | application no. | a supervisor replaces it correctly | 200 and one audit row | (200, 1) | PASS |
| 67 | D05 | step order | register a customer with no documents (typed by hand) | 400 | (400, 'cannot register: upload the bill and Aadhaar and chec | PASS |
| 68 | D05 | step order | accept before registering | 400 | 400 | PASS |
| 69 | D05 | step order | send the agreement before the vendor accepted (Registration) | 400 | (400, 'cannot send the agreement: accept the customer in the | PASS |
| 70 | R8 | step order | send the agreement before the vendor accepted (Close-out route) | 400 | (400, 'not ready to send: Vendor-consumer agreement (Missing | PASS |
| 71 | R4 | co-pilot | number read off the portal for a customer Solara thought not ready | kept (the portal registered them) | (200, '') | PASS |
| 72 | R2 | extraction | confirm the bill's mobile when the owner typed another | the typed mobile (the OTP phone) kept | (200, '9890022222') | PASS |
| 73 | R3 | extraction | confirm the consumer number with 'abc' | 400 | (400, 'the consumer number has digits only (spaces and hyphe | PASS |
| 74 | R3 | extraction | confirm it as '1700 5550 1234' | stored as 170055501234 | (200, '') | PASS |
| 75 | R11 | extraction | a hand correction to the bill, then a new bill uploaded | the new bill's reading wins | LT-I RES | PASS |
| 76 | R12 | registration page | sanctioned load read as '3.5 kW approx.' | the page loads (no 500) | 200 | PASS |
| 77 | P3 | details | a customer with no email | 'email' listed as missing (the portal verifies it by OTP) | ['consumer number', 'mobile', 'email (the portal sends it an | PASS |
| 78 | D14 | e-sign page | ?error= with crafted text | the text is not shown | checked | PASS |
| 79 | M6 | e-sign page | wrong last-4 digits | told in English and Marathi, with the tries left | checked | PASS |
| 80 | R10 | e-sign page | a 9000x9000 'signature' (20 KB) | refused in under 2 s, server keeps serving | 0.02s | PASS |
| 81 | R7 | e-sign page | the customer signs as 'D’Souza Priya' (curly apostrophe) | signed | signed | PASS |
| 82 | R9 | e-sign evidence | a link sent before copies were kept is signed | a copy is kept at signing; the agreement verifies | verified | PASS |
| 83 | D15 | dashboard | GET /favicon.ico | no 404 | checked | PASS |
| 84 | P1 | co-pilot | manifest hosts | consumer. and vendor.pmsuryaghar.gov.in included | ['https://rts.mahadiscom.in/RoofTopSolarVendor/*', 'https:// | PASS |
| 85 | P2 | dashboard links | live 'Open customer registration' / 'Open vendor login' | the real login pages | {'pmsg': 'https://consumer.pmsuryaghar.gov.in/consumer/#/log | PASS |
| 86 | P4 | rules | valid.app_no on 8-digit MH numbers | NP-MHSED26-12345678 accepted | checked | PASS |
| 87 | E1 | details: district | the old name 'Ahmednagar' | saved as the portal's 'Ahilyanagar' | Ahilyanagar | PASS |
| 88 | E1 | details: district | 'Atlantis' | 400; not a district on the portal | (400, 'Atlantis is not a Maharashtra district on the portal; | PASS |
| 89 | E1 | extraction: district | Aadhaar QR says 'Aurangabad' | stored as 'Chhatrapati Sambhajinagar' | checked | PASS |
| 90 | E1 | dashboard | the district list | the portal's 36 Maharashtra districts | 36 | PASS |
| 91 | E2 | customer link | the customer opens it | 200, greets them by first name, WhatsApp to their own number | 200 | PASS |
| 92 | E2 | customer link | a viewer asks for a link | 403 | checked | PASS |
| 93 | E2 | customer link | the customer sends the bill PDF | stored, read like an owner upload, and the page says received | (303, ['address', 'amount', 'avg_units', 'bill_mobile']) | PASS |
| 94 | E2 | customer link | the page after the upload | shows received, never the bill's contents | checked | PASS |
| 95 | E2 | customer link | a document kind the link does not ask for | refused | /up/ypRt3ocMRorKHstDx2Vbx_t4?err=type | PASS |
| 96 | E2 | customer link | a wrong email | refused, nothing saved | /up/ypRt3ocMRorKHstDx2Vbx_t4?err=email | PASS |
| 97 | E2 | customer link | the customer types their email | saved on the record | link.c@example.com | PASS |
| 98 | E2 | customer link | a made-up link | 404 | checked | PASS |
| 99 | E2 | customer link | the 31st file on one link | refused; the owner sends a new link | /up/ypRt3ocMRorKHstDx2Vbx_t4?err=many | PASS |
| 100 | E2 | customer link | after 7 days | 410, expired | checked | PASS |
| 101 | E3 | co-pilot: My Application | a status Solara does not know, and a number on no customer | nothing marked; the status is reported | {'ok': True, 'updated': [], 'unknown': ['Something new (Pend | PASS |
| 102 | E3 | co-pilot: My Application | the customer listed as 'Upload Agreement (Pending)' | marked accepted in Solara, no click | [{'id': 'SS-2070', 'name': 'List Customer', 'what': 'accepte | PASS |
| 103 | E3 | co-pilot: My Application | the portal is past the agreement, Solara has no signed one | not marked uploaded; the gap is shown | {'ok': True, 'updated': [], 'unknown': [], 'problems': [{'id | PASS |
| 104 | M3 | details form | the email box | marked as needed (*), not 'optional' | Email * | PASS |
| 105 | M4 | details form | type 3 into the highlighted capacity box | the 'missing' highlight goes as soon as it has a value | (True, False) | PASS |
| 106 | M5 | details form | type 210000 as the cost | read back as Rs 2,10,000 (a missed zero shows) | Rs 2,10,000 | PASS |
| 107 | U7 | Registration screen | a new customer (next step: documents) | Documents first and open; the portal section folded | {'first': 'regDocs', 'open': True, 'portal': False, 'body':  | PASS |
| 108 | U8 | Registration screen | text size and labels | body 15px; labels at least 13px, not in capitals | {'first': 'regDocs', 'open': True, 'portal': False, 'body':  | PASS |
| 109 | U9 | Registration screen | open the folded portal section, then the screen redraws | it stays open | [True, True] | PASS |
| 110 | E4 | Registration screen | tap the 3 kW button | capacity filled with 3; the button shows it is picked | ['3', '3 kW'] | PASS |
| 111 | E4 | Registration screen | the district box | a list of the portal's districts, not a text box | SELECT:37 | PASS |

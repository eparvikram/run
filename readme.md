Project Structure (Recommended for Enterprise):

your_project_root/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI application
│   ├── models.py           # Pydantic models for API requests/responses
│   ├── services.py         # Contains your LangGraph workflow
│   └── utils.py            # Helper functions like parse_code_blocks
├── .env                    # For environment variables like OPENAI_API_KEY
├── requirements.txt        # Project dependencies
└── run.sh                  # Simple script to run the FastAPI app (for dev/testing)

How to Run and Test:

Set up the environment:

Create the project structure as described.
Fill in requirements.txt and install: pip install -r requirements.txt.
Populate your .env file with actual keys.
Start the FastAPI server:

Open your terminal in your_project_root.
Run: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload (for development)
Or execute ./run.sh
Interact with the API (e.g., using Postman, Insomnia, or a simple Python script):

Endpoint 1: /generate-code (POST)

URL: http://localhost:8000/generate-code

Method: POST

Headers:

Content-Type: application/json
X-API-Key: a-very-secret-key-for-your-frontend (Use the key from your .env)
Body (JSON):

JSON

{
    "tdd_text": [
        "This document outlines the design for a simple Loan Application and Customer Management System.\nFrontend: React\n\n**Customer-facing UI Components:**\n- CustomerRegistrationForm (fields: username, email, password, confirmPassword)\n- CustomerLoginForm (fields: email, password)\n- LoanApplicationForm (fields: loanAmount, loanTerm, purpose, annualIncome)\n- UserDashboard (displays: current loans, application status)"
    ]
}
Expected Response (Status 202 Accepted):

JSON

{
    "message": "Code generation started. Please use the provided URL to check for the zip file soon.",
    "zip_download_url": "/download-zip/temp_zips_api/generated_code_YYYYMMDDHHMMSSFFFFFF"
}
(The zip_download_url will contain dynamic unique folder names like generated_code_YYYYMMDDHHMMSSFFFFFF and zips_YYYYMMDDHHMMSSFFFFFF)

Endpoint 2: /download-zip/{zip_base_dir}/{code_base_dir} (GET)

URL: Use the zip_download_url provided in the generate-code response. For example: http://localhost:8000/download-zip/temp_zips_api/generated_code_20250623183000123456 (replace with actual path)
Method: GET
Headers:
X-API-Key: a-very-secret-key-for-your-frontend
Expected Response: A downloadable zip file. If not ready, you'll get a 404. Your frontend team would implement a polling mechanism to check this URL periodically until the zip file is available.


{
  "tdd_text": [
    "Loan Application Tracking System (LATS) - High-Level Design Document\n\n1. Introduction\nThe Loan Application Tracking System (LATS) will provide a web-based platform for customers to apply for loans and track their application status in real-time. It will also include an admin dashboard for bank staff to efficiently review, approve, or reject loan applications. The system aims to replace the current manual or semi-digital workflow, improving customer experience and operational efficiency.\n\n2. Architectural Overview\n2.1 System Design Approach\nThe system will be developed using a layered architecture to promote scalability, security, and maintainability. The architecture will consist of the following layers:\n1. Presentation Layer: Handles user interaction through the customer portal and admin dashboard.\n2. Application Layer: Implements business logic for loan application processing, status updates, and notifications.\n3. Data Layer: Manages storage and retrieval of structured data (e.g., loan applications, user profiles).\n4. Integration Layer: Facilitates communication between system components via RESTful APIs.\n5. Security Layer: Ensures secure data transmission and authentication mechanisms.\n\n2.2 Deployment Model\nThe system will be deployed on a cloud platform (AWS or Azure) to ensure scalability, reliability, and flexibility. The deployment model will use containerization (e.g., Docker) for efficient resource management and consistent environments across development, testing, and production stages.\n\n3. Technical Design Details\n3.1 Frontend Design\nTechnology Stack:\n- Framework: Angular\n- Languages: HTML5, CSS3, JavaScript/TypeScript\nFeatures:\n- Customer registration and login with two-factor authentication (2FA).\n- Loan application form with dynamic validation for required fields.\n- Real-time application status tracking.\n- Responsive design for compatibility across desktops, tablets, and smartphones.\nKey Components:\n- Customer Portal:\n  - Loan Application Submission Interface\n  - Status Tracking Dashboard\n- Admin Dashboard:\n  - Loan Application Review and Management Interface\n  - Reporting Dashboard for loan statistics.\n3.2 Backend Design\nTechnology Stack:\n- Framework: Python (Django or Flask)\n- Database: PostgreSQL\nFeatures:\n- Application submission processing.\n- Workflow management for application status updates (Submitted, Under Review, Approved, Rejected).\n- Role-based access control for admin dashboard users.\nKey Components:\n- Business Logic: Implements loan application lifecycle workflows.\n- Notification Engine: Triggers email/SMS notifications for status changes.\n- API Layer: RESTful APIs for communication between frontend and backend.\nDatabase Design - Tables:\n- Users: Stores customer and bank staff profiles.\n- Applications: Stores loan application details.\n- Status History: Logs changes in application status over time.\n- Notifications: Tracks notification delivery for audit purposes.\n\n3.3 API Design\nKey Endpoints:\n1. Submit Loan Application\n- Endpoint: /api/loan/application/submit\n- Method: POST\n- Request Example:\n{ \"customer_id\": \"12345\", \"loan_amount\": 50000,\n\"tenure\": 24, \"purpose\": \"Home Renovation\" }\n- Response Example:\n{ \"status\": \"Success\", \"application_id\":\n\"67890\", \"message\": \"Loan application submitted\nsuccessfully\" }\n2. Fetch Application Status\n- Endpoint: /api/loan/application/status\n- Method: GET\n- Request Parameters: { \"application_id\": \"67890\" }\n- Response: { \"application_id\": \"67890\",\n\"status\": \"Under Review\", \"updated_at\":\n\"2023-10-01T10:00:00Z\" }\nAPI Security:\n- OAuth2-based authentication for securing endpoints.\n- Rate limiting to prevent abuse.\n3.4 Security Design\n- Data Transmission: SSL encryption to secure data in transit.\n- Data Storage: AES-256 encryption for sensitive data at rest.\n- Authentication: Multi-Factor Authentication (MFA) for all users.\n- Access Control: Role-based access for admin dashboard users.\n- Monitoring: Regular audits and real-time threat detection.\n\n3.5 Notification Design\nIntegration:\n- Email Gateway: SMTP-based\n- SMS Gateway: Twilio\nWorkflow:\n1. Status update triggers the notification engine.\n2. Engine sends email/SMS to customer.\n3. Delivery status is logged for auditing.\n3.6 Hosting and Deployment\nCloud Platform: AWS or Azure for scalable and reliable hosting.\nDeployment Tools:\n- Containerization: Docker\n- Orchestration: Kubernetes\nRedundancy and Failover:\n- Load balancing\n- Automatic failover mechanisms\n4. Assumptions and Dependencies\nAssumptions:\n1. End users have internet access and valid contact info.\n2. Loan approval criteria are pre-defined.\n3. Bank staff will be trained on dashboard usage.\n\nDependencies: TBD\n5. Success Metrics and KPIs\nCustomer Experience:\n- Loan application submission < 5 minutes\n- 90% reduction in complaints\nOperational Efficiency:\n- 50% faster loan processing\n- Eliminate paper-based workflows\nSystem Performance:\n- 99.9% uptime\n- Notifications delivered in <30s for 95% of cases\n6. Risks and Mitigation Strategies\n1. Data Security Breaches: Mitigate via encryption and vulnerability testing.\n2. Development Delays: Use Agile practices.\n3. Low User Adoption: Awareness campaigns and training.\n4. Notification Failures: Use redundant gateways.\n5. System Downtime: Ensure 24/7 monitoring and failover.\n7. Conclusion\nThe Loan Application Tracking System (LATS) modernizes ABC Bank's loan processing, delivering a secure, efficient, and user-friendly digital experience."
  ]
}
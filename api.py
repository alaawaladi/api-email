import time
import os
import sys
import subprocess
from pydantic import BaseModel, EmailStr,validator,Field
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QMessageBox
from fastapi import FastAPI,HTTPException
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.options import Options as options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import shutil
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from email_validator import validate_email, EmailNotValidError
from fastapi.exceptions import RequestValidationError
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


app = FastAPI()
main_app = None
uvicorn_process = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Email Sender")

        self.start_button = QPushButton("Start API", self)
        self.start_button.setGeometry(10, 10, 150, 30)
        self.start_button.clicked.connect(self.start_api)

        self.stop_button = QPushButton("Stop API", self)
        self.stop_button.setGeometry(10, 50, 150, 30)
        self.stop_button.clicked.connect(self.stop_api)
        self.stop_button.setEnabled(False)

        self.status_label = QLabel("API Status: Not Running", self)
        self.status_label.setGeometry(10, 90, 200, 30)

    def start_api(self):
        global main_app, uvicorn_process
        main_app = QApplication(sys.argv)

        uvicorn_cmd = ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
        uvicorn_process = subprocess.Popen(uvicorn_cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("API Status: Running")
     
    def stop_api(self):
        global uvicorn_process
        if uvicorn_process is not None:
            uvicorn_process.terminate()
            uvicorn_process.wait()
            uvicorn_process = None

            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_label.setText("API Status: Not Running")
        else:
            QMessageBox.warning(self, "Error", "API is not running.")
#************** start api section ********************#           
class EmailFormatException(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Invalid email format: {email}")

class EmailRequest(BaseModel):
    subject: str = Field(..., title="Subject", description="Email subject", max_length=100)
    email_list: list[EmailStr] = Field(..., title="Email List", description="List of recipient emails")
    body: str = Field(..., title="Body", description="Email body", max_length=1000)
    options: dict = Field({}, title="Options", description="Additional options for sending the email")

    @validator('email_list')
    def validate_email_list(cls, email_list):
        validated_emails = []
        for email in email_list:
            try:
                validated_email = validate_email(email)
                validated_emails.append(validated_email.email)
            except EmailNotValidError:
                raise ValueError(f"Invalid email format: {email}")
        return validated_emails
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_messages = []
    for error in exc.errors():
        loc = ".".join(map(str, error["loc"]))
        message = error["msg"]
        error_messages.append(f"{loc}: {message}")
    return JSONResponse(status_code=422, content={"detail": error_messages})


@app.post("/send-email")
async def handle_send_email(request_data: EmailRequest):
    subject = request_data.subject.strip()
    email_list = request_data.email_list
    body = request_data.body.strip()
    options = request_data.options
    selected_profiles = options.get("selected_profiles", [])

    errors = []

    if not subject:
        errors.append("Subject field is required.")
    if not email_list or all(email.strip() == '' for email in email_list):
        errors.append("Email list field is required.")
    elif not all(validate_email(email.strip()) for email in email_list):
        raise EmailFormatException("Invalid email format in the email list.")
    if not body:
        errors.append("Body field is required.")
    if not selected_profiles or all(profile.strip() == '' for profile in selected_profiles):
        errors.append("Selected profiles field is required.")

    if errors:
        raise HTTPException(status_code=400, detail=errors[0])

    for email in email_list:
        for profile_path in selected_profiles:
            try:
                send_email(email, subject, body, profile_path)
            except EmailFormatException as e:
                raise HTTPException(status_code=422, detail=str(e))
    
    return {"message": "Email sent successfully."}


@app.get("/profiles")
async def get_profiles():
    profiles_path = "C:/Users/al.waladi/AppData/Local/Mozilla/Firefox/Profiles"
    profiles = []
    
    if os.path.exists(profiles_path) and os.path.isdir(profiles_path):
        profiles = os.listdir(profiles_path)
    
    return {"profiles": profiles}
@app.get("/profiles/{profile_name}")
async def check_profile_login(profile_name: str,self):
    profiles_path = "C:/Users/al.waladi/AppData/Local/Mozilla/Firefox/Profiles"
    profile_directory = os.path.join(profiles_path, profile_name)

    if not os.path.exists(profile_directory) or not os.path.isdir(profile_directory):
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found.")

    firefox_options = FirefoxOptions()
    firefox_options.headless = True

    try:
        self.driver = webdriver.Firefox(options=firefox_options, firefox_profile=profile_directory)

        self.driver.get("https://mail.google.com")
        time.sleep(10)
        # Check if the profile is logged in or not
        if "Sign in" in self.driver.title:
            login_status = False
        else:
            login_status = True

        self.driver.quit()

        return {"profile": profile_name, "login_status": login_status}
    except Exception as e:
        # Handle any exceptions that occur during the login check
        return {"error": str(e)}



#*******************************************************


def send_email(recipient, subject, body, selected_profiles,self):
    new_profile_directory = os.path.join(os.getcwd(), "new_profile")
    if not os.path.exists(new_profile_directory):
        os.makedirs(new_profile_directory)

    selected_profile_directory = selected_profiles.split("\\")[-1]
    new_profile_path = os.path.join(new_profile_directory, selected_profile_directory)

    if not os.path.exists(new_profile_path):
        shutil.copytree(selected_profiles, new_profile_path)

    # Set GeckoDriver options
    geckodriver_options = webdriver.FirefoxOptions()
    geckodriver_options.headless = False  # Set to True if you want to hide the browser window

    # Launch Firefox with GeckoDriver
    self.driver = webdriver.Firefox(
        executable_path=r"C:\Users\al.waladi\Desktop\check\api\drivers\geckodriver.exe",
        options=geckodriver_options,
        firefox_profile=new_profile_path
    )

    self.driver.get("https://mail.google.com/mail/u/0/#inbox?compose=new")
    time.sleep(5)
    # Wait for the recipient input field to be visible
    wait = WebDriverWait(self.driver, 10)
    recipient_input = wait.until(EC.visibility_of_element_located((By.XPATH, '//div/input[@peoplekit-id="BbVjBd"]')))
    recipient_input.send_keys(recipient)
    time.sleep(1)
    recipient_input.send_keys(Keys.ESCAPE)
    time.sleep(1)
    # subject
    subject_field = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@name="subjectbox"]')))
    subject_field.send_keys(subject)
    time.sleep(1)
    # body
    body_field = wait.until(EC.visibility_of_element_located((By.XPATH, '//div[@role="textbox"]')))
    body_field.send_keys(body)

    time.sleep(2)
    try:
        ActionChains(self.driver, 0.5).key_down(Keys.CONTROL).send_keys(Keys.RETURN).key_up(Keys.CONTROL).perform()
    except Exception:
        pass

    try:
        WebDriverWait(self.driver, 30).until(EC.visibility_of_element_located((By.XPATH, '//*[@id="link_vsm"]')))
    except Exception:
        pass
        # Perform actions on the elements

    time.sleep(3)
    self.driver.quit()

if __name__ == "__main__":
    app_window = QApplication([])
    main_window = MainWindow()
    main_window.show()
    sys.exit(app_window.exec())

'''


'''
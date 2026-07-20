import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

class EducationDetails10(BaseModel):
    board: str
    passing_year: str
    marks: str
    percentage: str
    marksheet_link: str

class EducationDetails12(BaseModel):
    board: str
    passing_year: str
    stream: str
    marks: str
    percentage: str
    marksheet_link: str

class GraduationDetails(BaseModel):
    university: str
    degree: str
    passing_year: str
    marks: str
    percentage: str
    marksheet_link: str

class PostGraduationDetails(BaseModel):
    university: str
    degree: str
    passing_year: str
    marks: str
    percentage: str
    marksheet_link: str

class ExperienceDetails(BaseModel):
    total_years_months: str
    experience_letter_link: str

class CandidateDetails(BaseModel):
    candidate_name: str
    candidate_email: str
    date_of_birth: str
    mobile_number: str
    gender: str
    state: str
    tenth: EducationDetails10 = Field(alias="10th")
    twelfth: EducationDetails12 = Field(alias="12th")
    graduation: GraduationDetails
    post_graduation: PostGraduationDetails
    experience: ExperienceDetails
    resume_link: str

try:
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    print("Testing gemini-3.5-flash with Pydantic list[CandidateDetails] response_schema...")
    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents='Extract candidate: John Doe, email john@example.com, born 12/12/1990, phone 1234567890, male from NY. 10th CBSE 2006 400/500 (80%) in x.pdf. B.Tech from MIT in 2012 with 8.5 CGPA in grad.pdf. 3 years experience at Google in exp.pdf. Resume is cv.pdf.',
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[CandidateDetails],
        )
    )
    print("SUCCESS! Response text:")
    print(response.text)
except Exception as e:
    print("FAILED:", str(e))

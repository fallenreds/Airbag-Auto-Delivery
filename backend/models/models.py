from pydantic import BaseModel



class BaseTemplate(BaseModel):
    """Used for creating template"""
    name:str
    text:str

class Template(BaseTemplate):
    """Used for getting template"""
    id:int


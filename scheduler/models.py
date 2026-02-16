"""Pure data structures. No business logic."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str
    gender: str
    grad_year: int


@dataclass(frozen=True)
class Request:
    student_id: str
    class_code: str


@dataclass(frozen=True)
class Course:
    class_code: str
    dept_code: str
    name: str
    duration_flag: str  # F1, etc.
    semester_flag: str  # S1, S2


@dataclass(frozen=True)
class Assignment:
    student_id: str
    class_code: str


@dataclass(frozen=True)
class Conflict:
    student_id: str
    class_code: str
    reason: str

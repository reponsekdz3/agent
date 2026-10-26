def totalmarks(marks):
    sumofmarks = sum(marks)
    return sumofmarks

def average(marks):
    return sum(marks) / len(marks)

def grades(marks):
    if marks >= 80:
        return "A"
    elif marks >= 70:
        return "B"
    elif marks >= 60:
        return "C"
    elif marks >= 50:
        return "D"
    elif marks >= 40:
        return "E"
    elif marks <= 39:
        return "F"
    else:
        return "invalid marks"

students = []
passed = 0
failed = 0
print(f"Welcome back to the school mark and report program")

count = int(input(f" enter number of students you want to insert : "))

for i in range(1, count + 1):
    stfname = input(f"enter first name of the student : ")
    stlname = input(f"enter last name of the student : ")

    print(f"now you are going to record  marks of {stfname} {stlname}")
    stmarksinmat = int(input(f"enter marks in math : "))
    stmarkseng = int(input(f"enter marks in english : "))
    stmarkpy = int(input(f"enter marks in python : "))

    totalstmarks = totalmarks((stmarksinmat, stmarkseng, stmarkpy))
    avg = average((stmarksinmat, stmarkseng, stmarkpy))

    gradesofstudent = grades(avg)

    if avg >= 50:
        passed += 1
    else:
        failed += 1

    students.append((stfname, stlname, stmarksinmat, stmarkseng, stmarkpy))

for firstname, lastname, math, eng, py in students:
    total = totalmarks((math, eng, py))
    avg = average((math, eng, py))
    grade = grades(avg)
    print(f"Names: {firstname} {lastname} | Total: {total} | Avg: {avg} | Grade: {grade}")

print(f"Class summary: Passed = {passed} | Failed = {failed}")
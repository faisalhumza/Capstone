import glob
#import RPi.GPIO as GPIO # Uncomment when running on the pi
import time
import boto3

import face_recognition
from flask import jsonify, send_from_directory
from flask_uploads import UploadSet, IMAGES, configure_uploads
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SubmitField
from threading import Thread
from datetime import datetime

from ALPR import *
from dbFunc import *
from dbFunctions import find_lp_owner



# Initialize app
app = Flask(__name__, static_url_path='', )
gAddress = ""

# Code needed for image uploading
app.config['SECRET_KEY'] = 'capstone123'
app.config['UPLOADED_PHOTOS_DEST'] = 'uploads'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

photos = UploadSet('photos', IMAGES)
configure_uploads(app, photos)

sns_client = boto3.client(
    'sns',
    region_name='ca-central-1',
    aws_access_key_id='',
    aws_secret_access_key=''
)

class UploadForm(FlaskForm):
    photo = FileField(
        validators=[
            FileAllowed(photos, 'Only images are allowed.'),
            FileRequired('File field should not be empty.')
        ]
    )
    submit = SubmitField('Upload')


currentName = ""
percent_accuracy = None
display_lpResult = ""
display_oResult = ""
display_iResult = ""
display_cResult = ""

### NOTE: All images must have the following format to loaded and read properly:  'name.jpg' ####

# Create arrays of known face encodings and their names
known_face_names = list()
known_face_encodings = list()

# Load all images names into lists 

images = (os.listdir('images/'))
imagesRGB = [face_recognition.load_image_file(file) for file in glob.glob('images/*.jpg')]

# Add the known names as strings into an array & process their encodings
for i in range(len(images)):
    known_face_names.append(images[i][:-4])
    sample_face_encoding = face_recognition.face_encodings(imagesRGB[i])[0]
    known_face_encodings.append(sample_face_encoding)

process_this_frame = True


def gen_frames(debug=False, filename=None):
    """Generates facial predictions either from camera or local files"""
    if not debug:
        camera = cv2.VideoCapture(0)

    while True:
        if debug:
            frame = cv2.imread(filename)
            success = True
        else:
            success, frame = camera.read()
        if not success:
            break
        else:
            # Resize frame of video to 1/4 size for faster face recognition processing
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
            rgb_small_frame = small_frame[:, :, ::-1]

            # Find all the faces and face encodings in the current frame of video
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            face_names = []
            for face_encoding in face_encodings:
                # See if the face is a match for the known face(s)
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                name = "Unknown"
                # Or instead, use the known face with the smallest distance to the new face
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)

                ## Calculate the accuracy of the face detected (compared with the highest matched face)
                global percent_accuracy
                percent_accuracy = np.round((1 - face_distances[best_match_index]) * 100, 2)
                if matches[best_match_index] and percent_accuracy >= 50:
                    name = known_face_names[best_match_index]

                face_names.append(name)  ## Label of the image being matched!

                ## Only print accuracy if it redetects a new person/unknown
                global currentName
                if ((name != currentName) or debug):
                    print("Accuracy: " + str(percent_accuracy) + "% " + name)

                currentName = name

            # Display the results
            for (top, right, bottom, left), name in zip(face_locations, face_names):
                # Scale back up face locations since the frame we detected in was scaled to 1/4 size
                top *= 4
                right *= 4
                bottom *= 4
                left *= 4

                # Draw a box around the face
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)

                # Draw a label with a name below the face
                cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 0, 255), cv2.FILLED)
                font = cv2.FONT_HERSHEY_DUPLEX
                cv2.putText(frame, name, (left + 6, bottom - 6), font, 1.0, (255, 255, 255), 1)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def log_person():
    return currentName


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/lpPage', methods=['GET', 'POST'])
def lpPage():
    form = UploadForm()
    if form.validate_on_submit():
        filename = photos.save(form.photo.data)
        file_url = url_for('get_file', filename=filename)
        global display_lpResult
        display_lpResult = readLP(filename)

        # Initialize database connection
        con = sqlite3.Connection('Database.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # dbQuery = None if the plate isnt in the database
        dbQuery = find_lp_owner(display_lpResult, cur)
        print(dbQuery)
        print(type(dbQuery))
        global display_oResult
        global display_iResult
        global display_cResult
        if dbQuery is None:
            display_oResult = "Not Found"
            display_iResult = "Not Found"
            display_cResult = "Not Found"
        else:
            display_oResult = dbQuery['Owner']
            display_iResult = dbQuery['Info']
            display_cResult = dbQuery['Colour']
            #if(display_cResult == "red"):
            #        t = Thread(target=buzz_for_5_seconds)
            #        t.start()
            


        # Close connection to database
        con.close()

        print("Uploaded file: " + filename)  ## Variable 'filename' stores the name of the image selected, e.g. im4.png
    else:
        file_url = None
    my_string = ""
    return render_template('lpPage.html', form=form, file_url=file_url,
                           display_lpResult=display_lpResult, display_oResult=display_oResult, display_iResult=display_iResult,
                           display_cResult=display_cResult,
                            my_string=display_cResult)


@app.route('/fPage', methods=['GET', 'POST'])
def fPage():
    if request.method == 'POST':
        return redirect(url_for('index'))
    return render_template('fPage.html', displayName=currentName, displayAccuracy=str(percent_accuracy) + " %")


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/uploads/<filename>')
def get_file(filename):
    return send_from_directory(app.config['UPLOADED_PHOTOS_DEST'], filename)


@app.route("/currentName")
def updateCurrentName():
    return f"{currentName}"


@app.route("/displayAccuracy")
def updateAccuracy():
    return str(percent_accuracy) + "%"


@app.route('/markers')
def get_markers_data():
    conn = sqlite3.connect('Database.db')
    c = conn.cursor()
    c.execute('SELECT latitude, longitude, name, date, time, threat, location FROM Markers')
    data = c.fetchall()
    conn.close()
    markers = []
    for item in data:
        markers.append({
            'lat': item[0],
            'lng': item[1],
            'name': item[2],
            'date': item[3],
            'time': item[4],
            'threat': item[5],
            'location': item[6]
        })
    return jsonify(markers)




# Helper function to get the color of the threat for a specific Criminal
def getThreatLevel(name):
    conn = sqlite3.connect('Database.db')
    c = conn.cursor()
    c.execute('SELECT Colour FROM Criminals WHERE name = ?', (name,))
    data = c.fetchone()
    conn.close()
    return data[0]


@app.route('/insert_marker', methods=['POST'])
def insert_marker():
    data = request.get_json()
    name = data['name']
    latitude = data['latitude']
    longitude = data['longitude']
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date, time = timestamp.split(' ')
    threat = data['threat']
    location = data['address'] # get the value of gAddress

    conn = sqlite3.connect('Database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM Markers WHERE name=?", (name,))
    existing_marker = c.fetchone()

    if existing_marker is None:
        c.execute("INSERT INTO Markers (name, latitude, longitude, date, time, threat, location) VALUES (?, ?, ?, ?, ?, ?, ?)", (name, latitude, longitude, date, time, threat, location))
        conn.commit()
        response = {'status': 'success', 'date': date, 'time': time}
    else:
        response = {'status': 'error', 'message': 'Marker with this name already exists'}

    conn.close()

    return jsonify(response)



@app.route('/send-text', methods=['POST'])
def send_text():
    data = request.get_json()
    phone_number = data['phone_number']
    name = data['name']
    latitude = data['latitude']
    longitude = data['longitude']
    date = data['date']
    time = data['time']
    threat = data['threat']
    message = f'Alert: {name} is detected! Location: ({latitude}, {longitude}) Date: {date} Time: {time} Threat: {threat}'
    response = sns_client.publish(
        PhoneNumber=phone_number,
        Message=message
    )
    return jsonify({'message': 'Text message sent!'})


@app.route('/alarm.mp3')
def play_alarm():
    return send_from_directory(app.static_folder, 'alarm.mp3')


@app.route('/criminals')
def get_criminals_data():
    conn = sqlite3.connect('Database.db')
    c = conn.cursor()
    c.execute('SELECT * FROM Criminals')
    data = c.fetchall()
    conn.close()
    criminals = []
    for item in data:
        criminals.append({
            'Name': item[0],
            'Crime': item[1],
            'Colour': item[2],
        })
    return jsonify(criminals)



def test1():
    """All results are unknown means very low false positives, what is good result"""
    for i in range(100):
        gen = gen_frames(debug=True, filename="test/face_image_" + str(i) + ".jpg")

        print(i)
        gen.__next__()

        gen.close()


def test2():
    """Shows only recognizable faces"""
    for i in ("Ahmad", "Humza", "Leonardo", "Mohamad",):
        gen = gen_frames(debug=True, filename="images/" + i + ".jpg")

        print(i)
        gen.__next__()

        gen.close()

# def buzz_for_5_seconds():
#     BuzzerPin = 4

#     GPIO.setmode(GPIO.BCM)
#     GPIO.setup(BuzzerPin, GPIO.OUT) 
#     GPIO.setwarnings(False)

#     global Buzz 
#     Buzz = GPIO.PWM(BuzzerPin, 440) 
#     Buzz.start(50) 
#     A4=440
#     song = [A4]
#     beat = [1]

#     for i in range(0, int(5 / 0.13)):
#         Buzz.ChangeFrequency(song[0])
#         time.sleep(beat[0]*0.13)

#     Buzz.stop()
#     GPIO.cleanup()


if __name__ == '__main__':
    # test1()
    # test2()
    app.run(host='0.0.0.0', debug=True, threaded=True, ssl_context='adhoc')



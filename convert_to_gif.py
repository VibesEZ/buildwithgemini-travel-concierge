import imageio
from PIL import Image

def convert_webm_to_gif(input_path="agent_demo.webm", output_path="agent_demo.gif", fps=5, max_width=500):
    print(f"Reading video from {input_path}...")
    reader = imageio.get_reader(input_path)
    meta = reader.get_meta_data()
    original_fps = meta.get('fps', 25)
    step = max(1, int(original_fps / fps))

    frames = []
    print("Processing and resizing frames for fast GIF generation...")
    for i, frame in enumerate(reader):
        if i % step == 0:
            img = Image.fromarray(frame)
            if img.width > max_width:
                height = int(img.height * (max_width / img.width))
                img = img.resize((max_width, height), Image.Resampling.NEAREST)
            img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
            frames.append(img)

    print(f"Saving optimized looping GIF ({len(frames)} frames) to {output_path}...")
    if frames:
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0
        )
        print(f"Successfully created {output_path}!")

if __name__ == "__main__":
    convert_webm_to_gif()
